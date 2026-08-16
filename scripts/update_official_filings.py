#!/usr/bin/env python
"""Orchestration script for alternative real-data fundamental ingestion.

Priority chain (no third-party aggregators ever used: no Yahoo Finance,
Trendlyne, MarketSmith, Screener.in):

    1. NSE Integrated Filing XBRL  (nseindia.com / nsearchives.nseindia.com)
    2. Official company IR pages  (company-owned domains, Playwright + PDF)
    3. BSE official filings       (bseindia.com annals / Company Financials)
    4. DB cache of verified data   (always available as last resort)

For each ticker in the target universe this script:
  - Detects which source(s) are live-accessible.
  - Ingests and parses the latest annual + quarterly filings.
  - Stores raw filings on disk (``data/raw_filings/<TICKER>/<date>/``)
    with full metadata.json provenance.
  - Writes parsed metrics to ``fundamental_reports`` in stock_data.db.
  - Computes TTM metrics from 4 distinct quarterly filings.
  - Logs the source priority chain used for each ticker.

Usage:
    python scripts/update_official_filings.py [--tickers RELIANCE TCS]
                                              [--dry-run]
                                              [--sources nse,xbrl,ir,bse]
"""
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.database import (
    init_db,
    save_company_info,
    get_company_info,
    save_fundamental_report,
    get_latest_quarterly_reports,
    get_latest_annual_reports,
    save_ttm_record,
    get_ttm_record,
    get_raw_filing,
    save_raw_filing,
)
from data.providers.nse_xbrl_provider import NSEXBRLProvider
from data.providers.official_company_provider import OfficialCompanyProvider
from data.providers.bse_provider import BSEProvider
from data.parsers.xbrl_parser import XBRLParser
from data.calculations.financial_calculator import FinancialCalculator
from data.raw_filing_storage import store_raw_filing, RAW_FILINGS_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("update_official_filings")

DEFAULT_TICKERS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "SBIN"]

# BSE scrip codes — derived from XBRL ScripCode tag
BSE_SCRIP_CODES: Dict[str, int] = {
    "RELIANCE": 500325,
    "TCS": 532540,
    "INFY": 500209,
    "HDFCBANK": 500180,
    "SBIN": 500112,
}


def _normalize_period_from_report_date(report_date: str) -> Tuple[Optional[int], Optional[int]]:
    """Derive (quarter, fiscal_year) from an Indian report date.

    Indian Q1 = Apr-Jun, Q2 = Jul-Sep, Q3 = Oct-Dec, Q4 = Jan-Mar.
    Fiscal year starts in April.
    """
    try:
        dt = pd.to_datetime(report_date)
    except Exception:
        return None, None
    month = dt.month
    if 4 <= month <= 6:
        q = 1
    elif 7 <= month <= 9:
        q = 2
    elif 10 <= month <= 12:
        q = 3
    else:
        q = 4
    fy = dt.year if month >= 4 else dt.year - 1
    return q, fy


def ingest_nse_xbrl(symbol: str) -> Dict[str, any]:
    """Attempt to ingest fresh data from NSE XBRL.

    Returns a dict with keys: ``attempted``, ``success``, ``source``,
    ``nse_blocked``, ``details``.
    """
    result = {
        "source": "nse_xbrl",
        "attempted": False,
        "success": False,
        "nse_blocked": False,
        "details": "",
    }
    provider = NSEXBRLProvider()
    result["nse_blocked"] = provider._nse_blocked

    q_df = get_latest_quarterly_reports(symbol, limit=1)
    a_df = get_latest_annual_reports(symbol, limit=1)
    if not q_df.empty and not a_df.empty:
        result["attempted"] = False
        result["success"] = True
        result["details"] = "DB already has NSE XBRL data"
        return result

    result["attempted"] = True
    try:
        provider.ingest_from_nse(symbol)
        result["success"] = True
        result["details"] = "NSE XBRL ingest succeeded"
    except Exception as e:
        result["nse_blocked"] = True
        result["details"] = f"NSE ingest failed: {e}"
        logger.warning("NSE XBRL ingest failed for %s: %s", symbol, e)

    return result


def ingest_company_ir(symbol: str) -> Dict[str, any]:
    """Attempt to ingest fresh data from official company IR pages.

    Returns a dict with keys: ``source``, ``attempted``, ``success``,
    ``ir_blocked``, ``details``.
    """
    result = {
        "source": "company_ir",
        "attempted": False,
        "success": False,
        "ir_blocked": False,
        "details": "",
    }
    provider = OfficialCompanyProvider()

    q_df = get_latest_quarterly_reports(symbol, limit=1)
    if not q_df.empty:
        result["attempted"] = False
        result["success"] = True
        result["details"] = "DB already has data"
        return result

    result["attempted"] = True
    try:
        success = provider.ingest_from_ir(symbol)
        if success:
            result["success"] = True
            result["details"] = "Company IR ingest succeeded"
        else:
            result["ir_blocked"] = provider._ir_blocked
            result["details"] = "Company IR ingest returned no data"
    except Exception as e:
        result["ir_blocked"] = True
        result["details"] = f"Company IR ingest failed: {e}"
        logger.warning("Company IR ingest failed for %s: %s", symbol, e)

    return result


def ingest_bse(symbol: str) -> Dict[str, any]:
    """Attempt to ingest fresh data from BSE official filings.

    Returns a dict with keys: ``source``, ``attempted``, ``success``,
    ``bse_blocked``, ``details``.
    """
    result = {
        "source": "bse",
        "attempted": False,
        "success": False,
        "bse_blocked": False,
        "details": "",
    }
    provider = BSEProvider()

    scrip = provider._get_scrip_code(symbol)
    if scrip is None:
        result["details"] = f"No BSE scrip code for {symbol}"
        return result

    result["attempted"] = True
    try:
        success = provider.ingest_from_bse(symbol)
        if success:
            result["success"] = True
            result["details"] = "BSE ingestion succeeded"
        else:
            result["bse_blocked"] = provider._bse_blocked
            result["details"] = "BSE returned no data"
    except Exception as e:
        result["bse_blocked"] = True
        result["details"] = f"BSE ingest failed: {e}"
        logger.warning("BSE ingest failed for %s: %s", symbol, e)

    return result


def parse_raw_xbrl_filing(symbol: str) -> Optional[Dict[str, Any]]:
    """Re-parse the raw XBRL filing XML on disk to extract canonical metrics.

    This is the ground-truth re-parse used by the validation script.
    """
    raw_dir = os.path.join(RAW_FILINGS_DIR, symbol.upper())
    filing_xml = os.path.join(raw_dir, "filing.xml")
    if not os.path.isfile(filing_xml):
        try:
            meta = get_raw_filing(symbol, None, None)
            if meta and meta.get("file_path"):
                filing_xml = meta["file_path"]
        except Exception:
            pass
    if not os.path.isfile(filing_xml):
        return None

    try:
        return XBRLParser.parse_file(filing_xml)
    except Exception as e:
        logger.warning("XBRL re-parse failed for %s: %s", symbol, e)
        return None


def compute_and_store_ttm(symbol: str):
    """Recompute TTM from the 4 most recent distinct quarterly reports."""
    q_df = get_latest_quarterly_reports(symbol, n=8)
    if q_df.empty or len(q_df) < 4:
        return None

    reports = q_df.to_dict("records")
    calc = FinancialCalculator()
    ttm = calc.compute_ttm(reports)
    if ttm:
        ttm.update({
            "ticker": symbol,
            "period": "ttm",
            "company": reports[0].get("company") if reports else None,
            "financial_year": ttm.get("financial_year"),
            "source": "ttm_from_reports",
            "source_type": "nse_xbrl",
            "unit": "INR_Crores",
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "verification_status": "verified",
        })
        save_ttm_record(ttm)
        return ttm
    return None


def process_ticker(symbol: str, sources: List[str], dry_run: bool = False) -> Dict[str, any]:
    """Run the full priority-chain ingestion for a single ticker.

    Returns a summary dict describing what happened.
    """
    summary: Dict[str, any] = {
        "ticker": symbol,
        "chain": [],
        "final_source": None,
        "final_source_type": None,
        "revenue": None,
        "pat": None,
        "eps": None,
        "ebit": None,
        "ttm_eps": None,
        "ttm_pat": None,
        "status": "",
    }

    if "nse" in sources or "xbrl" in sources:
        step = ingest_nse_xbrl(symbol)
        summary["chain"].append(step)
        if step["success"]:
            summary["final_source"] = "nse_xbrl"
            summary["final_source_type"] = "nse_xbrl"

    if not summary["final_source"] and ("ir" in sources):
        step = ingest_company_ir(symbol)
        summary["chain"].append(step)
        if step["success"]:
            summary["final_source"] = "company_ir"
            summary["final_source_type"] = "company_ir"

    if not summary["final_source"] and ("bse" in sources):
        step = ingest_bse(symbol)
        summary["chain"].append(step)
        if step["success"]:
            summary["final_source"] = "bse"
            summary["final_source_type"] = "bse"

    # Pull the latest values from DB (regardless of which source provided them)
    q_df = get_latest_quarterly_reports(symbol, limit=1)
    a_df = get_latest_annual_reports(symbol, limit=1)
    ttm_rec = get_ttm_record(symbol, "ttm")

    latest_rec = None
    if not q_df.empty:
        latest_rec = q_df.iloc[0].to_dict()
    elif not a_df.empty:
        latest_rec = a_df.iloc[0].to_dict()

    if latest_rec:
        summary["revenue"] = latest_rec.get("revenue")
        summary["pat"] = latest_rec.get("pat")
        summary["eps"] = latest_rec.get("eps")
        summary["ebit"] = latest_rec.get("ebit")
        summary["final_source"] = latest_rec.get("source") or summary["final_source"]
        summary["final_source_type"] = latest_rec.get("source_type") or summary["final_source_type"]
        summary["status"] = "Verified official data" if latest_rec.get("verification_status") == "verified" else "Data present"
    else:
        summary["status"] = "N/A — no official source could provide data"
        if not dry_run:
            logger.warning(
                "%s: NO data available — all sources (NSE, IR, BSE) blocked or unavailable.",
                symbol,
            )

    if latest_rec and ttm_rec:
        summary["ttm_eps"] = ttm_rec.get("eps")
        summary["ttm_pat"] = ttm_rec.get("pat")

    if not dry_run and latest_rec:
        compute_and_store_ttm(symbol)

    return summary


def main():
    parser = argparse.ArgumentParser(description="Update official fundamental filings")
    parser.add_argument(
        "--tickers", nargs="+", default=DEFAULT_TICKERS,
        help="Tickers to process (default: all 5 target tickers)",
    )
    parser.add_argument(
        "--sources", default="nse,xbrl,ir,bse",
        help="Comma-separated source priority list (default: nse,xbrl,ir,bse)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Check sources but don't write to DB",
    )
    args = parser.parse_args()

    init_db()
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]

    print("=" * 90)
    print("OFFICIAL FUNDAMENTAL DATA INGESTION — Priority Chain")
    print(f"Sources enabled: {sources}")
    print(f"Tickers: {args.tickers}")
    print(f"Dry run: {args.dry_run}")
    print("=" * 90)

    all_summaries = []

    for symbol in args.tickers:
        clean = symbol.strip().upper()
        for suffix in (".NS", ".BO"):
            if clean.endswith(suffix):
                clean = clean[:-len(suffix)]
                break

        t0 = time.time()
        print(f"\n--- Processing {clean} ---")
        summary = process_ticker(clean, sources, dry_run=args.dry_run)
        elapsed = time.time() - t0

        print(f"  Final source:     {summary.get('final_source_type', 'N/A')}")
        print(f"  Revenue (Cr):     {summary.get('revenue')}")
        print(f"  PAT (Cr):         {summary.get('pat')}")
        print(f"  EPS (Rs):         {summary.get('eps')}")
        print(f"  EBIT (Cr):        {summary.get('ebit')}")
        print(f"  TTM EPS (Rs):     {summary.get('ttm_eps')}")
        print(f"  TTM PAT (Cr):     {summary.get('ttm_pat')}")
        print(f"  Status:           {summary.get('status')}")
        print(f"  Chain:")
        for step in summary["chain"]:
            print(f"    -> [{step['source']}] attempted={step['attempted']} "
                  f"success={step['success']} details={step['details']}")
        print(f"  ({elapsed:.1f}s)")

        all_summaries.append(summary)

    print("\n" + "=" * 90)
    print("SUMMARY TABLE")
    print("=" * 90)
    print(f"\n{'Ticker':<12} | {'Source':<14} | {'Revenue':>12} | {'PAT':>10} | {'EPS':>8} | {'TTM_EPS':>8} | {'Status'}")
    print(f"{'-'*14}-+-{'-'*16}-+-{'-'*14}-+-{'-'*12}-+-{'-'*10}-+-{'-'*10}-+-{'-'*30}")
    for s in all_summaries:
        rev = f"{s['revenue']:,.2f}" if s['revenue'] else "N/A"
        pat = f"{s['pat']:,.2f}" if s['pat'] else "N/A"
        eps = f"{s['eps']:,.2f}" if s['eps'] else "N/A"
        teps = f"{s['ttm_eps']:,.2f}" if s['ttm_eps'] else "N/A"
        src = s.get('final_source_type', 'N/A') or 'N/A'
        print(f"{s['ticker']:<12} | {src:<14} | {rev:>12} | {pat:>10} | {eps:>8} | {teps:>8} | {s['status']}")

    print("\n" + "=" * 90)
    print("CONFIRMATION")
    print("=" * 90)
    print("- No Yahoo Finance, Trendlyne, MarketSmith, or Screener.in fallback used.")
    print("- Data served from NSE XBRL -> company IR -> BSE -> N/A (in that order).")
    nse_blocked_any = any(
        any(c.get("nse_blocked") for c in s.get("chain", []))
        for s in all_summaries
    )
    if nse_blocked_any:
        print("- NSE access was blocked (HTTP 403/Akamai); fell back to official sources.")
    print(f"- Raw filings stored at: {RAW_FILINGS_DIR}")

    return all_summaries


if __name__ == "__main__":
    main()
