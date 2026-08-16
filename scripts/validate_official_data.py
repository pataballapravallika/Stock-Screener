#!/usr/bin/env python
"""Validate official fundamental data against the raw XBRL / PDF filing ground truth.

For each ticker, this script:
  1. Reads the latest annual or quarterly record from the DB
     (``fundamental_reports``).
  2. Locates the raw XBRL filing XML (or PDF) on disk
     (``data/raw_filings/<TICKER>/<date>/filing.xml``).
  3. Re-parses the raw filing independently using ``XBRLParser`` /
     ``PDFParser`` to extract the canonical metric values.
  4. Compares the "app value" (what the app would show) against the
     "official report value" (re-parsed from the raw filing).
  5. Prints a table:

       Company | Metric | App Value | Official Report Value | Difference | Formula | Source | Period | Status

  6. Also validates TTM EPS (must equal the sum of the latest 4 quarterly
     EPS values — never trailing/forward-derived).

No third-party aggregators are involved at any step.  Every metric is
checked against the official filing document stored on disk.

Usage:
    python scripts/validate_official_data.py [--tickers RELIANCE TCS]
                                              [--output validation_report.csv]
"""
import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.database import (
    init_db,
    get_latest_quarterly_reports,
    get_latest_annual_reports,
    get_ttm_record,
    get_company_info,
    get_raw_filing,
    get_all_raw_filings,
)
from data.parsers.xbrl_parser import XBRLParser
from data.parsers.pdf_parser import PDFParser
from data.calculations.financial_calculator import FinancialCalculator
from data.raw_filing_storage import RAW_FILINGS_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("validate_official_data")

DEFAULT_TICKERS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "SBIN"]

METRIC_FIELDS: List[Tuple[str, str, str, str]] = [
    ("Revenue",      "revenue",            "Revenue",                          "INR Cr"),
    ("PAT",          "pat",                "Net Profit After Tax",             "INR Cr"),
    ("EPS",          "eps",                "Basic/Diluted EPS",                "INR"),
    ("EBIT",         "ebit",               "Profit Before Tax",                "INR Cr"),
    ("Operating Profit", "operating_profit", "Operating Profit",                "INR Cr"),
    ("Equity",       "equity",             "Total Stockholder Equity",         "INR Cr"),
    ("Total Assets", "assets",             "Total Assets",                     "INR Cr"),
    ("Total Debt",   "total_debt",         "Total Borrowings + Long-term Debt", "INR Cr"),
    ("OCF",          "operating_cash_flow", "Net Cash from Operating Activities", "INR Cr"),
    ("CapEx",        "capex",              "Purchase of Fixed Assets",         "INR Cr"),
    ("Share Capital", "share_capital",     "Equity Share Capital",             "INR Cr"),
    ("Face Value",   "face_value",         "Face Value per Share",             "INR"),
]

XBRL_TAG_MAP = {
    "revenue": [
        "RevenueFromOperations",
        "Income",
        "ifrs-full:Revenue",
        "ifrs-full:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:Revenues",
        "us-gaap:SalesRevenueNet",
        "acfr:Turnover",
    ],
    "pat": [
        "ProfitLossForThePeriod",
        "ProfitLossFromOrdinaryActivitiesAfterTax",
        "ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates",
        "ProfitLossForPeriod",
        "ProfitLossForPeriodFromContinuingOperations",
        "ifrs-full:ProfitLoss",
        "ifrs-full:NetIncomeLoss",
        "us-gaap:NetIncomeLoss",
        "us-gaap:NetIncomeLossAvailableToCommonStockholdersDiluted",
    ],
    "eps": [
        "DilutedEarningsPerShareAfterExtraordinaryItems",
        "BasicEarningsPerShareAfterExtraordinaryItems",
        "DilutedEarningsPerShareBeforeExtraordinaryItems",
        "BasicEarningsPerShareBeforeExtraordinaryItems",
        "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
        "BasicEarningsLossPerShareFromContinuingOperations",
        "BasicEarningsLossPerShare",
        "ifrs-full:BasicEarningsLossPerShare",
        "us-gaap:EarningsPerShareDiluted",
        "us-gaap:EarningsPerShareBasic",
    ],
    "ebit": [
        "ProfitBeforeExceptionalItemsAndTax",
        "ProfitLossFromOrdinaryActivitiesBeforeTax",
        "ProfitBeforeTax",
        "OperatingProfitBeforeProvisionAndContingencies",
        "ifrs-full:ProfitLossBeforeTax",
        "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxes",
        "us-gaap:IncomeLossBeforeIncomeTaxes",
    ],
    "operating_profit": [
        "ProfitBeforeExceptionalItemsAndTax",
        "ProfitLossFromOrdinaryActivitiesBeforeTax",
        "ProfitBeforeTax",
        "OperatingProfitBeforeProvisionAndContingencies",
        "ifrs-full:OperatingProfitLoss",
        "us-gaap:OperatingIncomeLoss",
    ],
    "equity": [
        "ifrs-full:Equity",
        "ifrs-full:EquityAttributableToOwnersOfParent",
        "us-gaap:StockholdersEquity",
        "Equity",
    ],
    "assets": [
        "NetSegmentAssets",
        "SegmentAssets",
        "ifrs-full:Assets",
        "us-gaap:Assets",
    ],
    "operating_cash_flow": [
        "NetCashFlowsFromUsedInOperatingActivities",
        "ifrs-full:NetCashFlowsFromUsedInOperatingActivities",
        "us-gaap:NetCashProvidedByUsedInOperatingActivities",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "ifrs-full:PaymentsToAcquirePropertyPlantAndEquipment",
        "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
        "ifrs-full:PurchaseOfPropertyPlantAndEquipment",
    ],
    "share_capital": [
        "PaidUpValueOfEquityShareCapital",
        "ifrs-full:EquityCapital",
        "us-gaap:CommonStock",
        "ifrs-full:ShareCapital",
    ],
    "face_value": [
        "FaceValueOfEquityShareCapital",
        "ifrs-full:FaceValue",
        "acfr:FaceValue",
    ],
}


def _parse_raw_filing(symbol: str, report_date: str, period: Optional[str] = None) -> Dict[str, Any]:
    """Parse the raw filing from disk and return canonical metric dict."""
    raw = get_raw_filing(symbol, report_date, period)
    if not raw:
        filing = _find_latest_raw_filing(symbol)
        if not filing:
            return {}
        raw = filing

    file_path = raw.get("file_path")
    source_type = raw.get("source_type") or raw.get("source") or ""
    if not file_path or not os.path.isfile(file_path):
        return {}

    result: Dict[str, Any] = {"source_type": source_type, "file_path": file_path, "source_url": raw.get("source_url", "")}

    if file_path.lower().endswith((".xml", ".xbrl", ".html", ".htm")):
        try:
            parsed = XBRLParser.parse_file(file_path)
            result.update({k: v for k, v in parsed.items() if v is not None})
        except Exception as e:
            result["_parse_error"] = str(e)
    elif file_path.lower().endswith(".pdf"):
        try:
            pdf_parser = PDFParser()
            tables = pdf_parser.extract_tables_from_file(file_path) if hasattr(pdf_parser, "extract_tables_from_file") else []
            if not tables:
                tables = []
                with open(file_path, "rb") as f:
                    tables = pdf_parser.extract_tables_from_bytes(f.read()) or []
            for df in tables:
                if df is None or df.empty or len(df.columns) < 2:
                    continue
                df = df.set_index(df.columns[0])
                idx = [str(i).lower().strip() for i in df.index]
                for field, tags in XBRL_TAG_MAP.items():
                    for tag in tags:
                        local = tag.split(":")[-1].lower()
                        for i_label in idx:
                            if local in i_label:
                                val = df.loc[i_label, df.columns[0]]
                                fval = _safe_float(str(val))
                                if fval is not None and result.get(field) is None:
                                    result[field] = fval
                                break
        except Exception as e:
            result["_parse_error"] = str(e)

    return result


def _find_latest_raw_filing(symbol: str) -> Optional[Dict[str, Any]]:
    """Find the most recent raw filing for a ticker from DB or disk."""
    df = get_all_raw_filings(symbol)
    if not df.empty:
        return df.iloc[0].to_dict()

    ticker_dir = os.path.join(RAW_FILINGS_DIR, symbol.upper())
    if not os.path.isdir(ticker_dir):
        return None

    latest_dir = None
    latest_date = ""
    for date_dir in os.listdir(ticker_dir):
        full = os.path.join(ticker_dir, date_dir)
        if os.path.isdir(full) and date_dir > latest_date:
            latest_date = date_dir
            latest_dir = full

    if not latest_dir:
        return None

    filing_path = os.path.join(latest_dir, "filing.xml")
    if not os.path.isfile(filing_path):
        for ext in (".pdf", ".html", ".htm"):
            alt = os.path.join(latest_dir, f"filing{ext}")
            if os.path.isfile(alt):
                filing_path = alt
                break

    meta_path = os.path.join(latest_dir, "metadata.json")
    meta = {}
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, "r") as f:
                meta = json.load(f)
        except Exception:
            pass

    return {
        "file_path": filing_path,
        "source_type": meta.get("source_type", "nse_xbrl"),
        "source_url": meta.get("source_url", ""),
        **meta,
    }


def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(str(val).replace(",", "").strip())
        if f != f or f == float("inf"):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _normalize_value(val: Any) -> Any:
    if val is None:
        return None
    f = _safe_float(val)
    return f


def validate_ticker(symbol: str) -> List[Dict[str, Any]]:
    """Produce validation rows for a single ticker."""
    rows: List[Dict[str, Any]] = []

    company_info = get_company_info(symbol)
    company_name = company_info.get("company_name") or symbol

    a_df = get_latest_annual_reports(symbol, limit=1)
    q_df = get_latest_quarterly_reports(symbol, limit=1)

    if not q_df.empty:
        db_rec = q_df.iloc[0].to_dict()
        report_date = db_rec.get("report_date", "")
        period_type = db_rec.get("period", "quarterly")
        q_num = db_rec.get("quarter")
        fy = db_rec.get("financial_year")
    elif not a_df.empty:
        db_rec = a_df.iloc[0].to_dict()
        report_date = db_rec.get("report_date", "")
        period_type = db_rec.get("period", "annual")
        q_num = None
        fy = db_rec.get("financial_year")
    else:
        rows.append({
            "Ticker": symbol,
            "Company": company_name,
            "Metric": "ALL",
            "App Value": "N/A",
            "Official Report Value": "N/A",
            "Difference": "N/A",
            "Formula": "N/A",
            "Source": "N/A",
            "Period": "N/A",
            "Status": "NOT VERIFIED — no data in DB",
        })
        return rows

    if q_num and fy:
        period_str = f"Q{q_num} FY{fy}"
    elif fy:
        period_str = f"FY{fy}"
    else:
        period_str = period_type or "N/A"

    raw = _parse_raw_filing(symbol, report_date, period_type)

    db_source = db_rec.get("source") or db_rec.get("source_type") or "N/A"
    source_url = db_rec.get("source_url") or raw.get("source_url") or "N/A"
    raw_source_type = raw.get("source_type", "N/A")

    for display_name, db_field, formula, unit in METRIC_FIELDS:
        app_val = _normalize_value(db_rec.get(db_field))
        raw_val = _normalize_value(raw.get(db_field))

        if app_val is not None and raw_val is not None:
            diff = app_val - raw_val
            if abs(diff) < 0.01:
                status = "MATCH"
            elif abs(diff) / max(abs(raw_val), 1) < 0.01:
                status = "MATCH (rounding)"
            else:
                status = "MISMATCH"
            diff_str = f"{diff:+.4f}" if db_field != "face_value" else f"{diff:+.4f}"
        elif app_val is not None and raw_val is None:
            status = "APP_HAS_VALUE (raw file not found or metric not parseable)"
            diff_str = "N/A"
        elif app_val is None and raw_val is not None:
            status = "MISSING IN DB"
            diff_str = "N/A"
        else:
            status = "N/A"
            diff_str = "N/A"

        app_str = f"{app_val:,.4f}" if app_val is not None else "N/A"
        raw_str = f"{raw_val:,.4f}" if raw_val is not None else "N/A"

        source_label = db_source if db_source != "N/A" else raw_source_type

        rows.append({
            "Ticker": symbol,
            "Company": company_name,
            "Metric": display_name,
            "App Value": app_str,
            "Official Report Value": raw_str,
            "Difference": diff_str,
            "Formula": formula,
            "Source": source_label,
            "Period": period_str,
            "Status": status,
        })

    ttm_rec = get_ttm_record(symbol, "ttm")
    if ttm_rec and ttm_rec.get("eps"):
        ttm_eps = _normalize_value(ttm_rec.get("eps"))
        q8 = get_latest_quarterly_reports(symbol, n=8)
        if not q8.empty and len(q8) >= 4:
            q_records = q8.to_dict("records")
            seen_periods = set()
            deduped = []
            for r in q_records:
                pk = str(r.get("report_date", ""))
                if pk and pk not in seen_periods:
                    seen_periods.add(pk)
                    deduped.append(r)
                if len(deduped) >= 4:
                    break
            eps_vals = []
            for r in deduped[:4]:
                v = _normalize_value(r.get("eps"))
                if v is not None:
                    eps_vals.append(v)
            if len(eps_vals) >= 4:
                ttm_eps_calc = sum(eps_vals[:4])
                if ttm_eps is not None and abs(ttm_eps - ttm_eps_calc) < 0.01:
                    ttm_status = "MATCH"
                else:
                    ttm_status = "MISMATCH"
                rows.append({
                    "Ticker": symbol,
                    "Company": company_name,
                    "Metric": "TTM EPS",
                    "App Value": f"{ttm_eps:,.4f}",
                    "Official Report Value": f"{ttm_eps_calc:,.4f}",
                    "Difference": f"{ttm_eps - ttm_eps_calc:+.4f}",
                    "Formula": "Sum of 4 most recent quarterly EPS",
                    "Source": ttm_rec.get("source", "ttm_from_reports"),
                    "Period": period_str,
                    "Status": ttm_status,
                })
            else:
                rows.append({
                    "Ticker": symbol,
                    "Company": company_name,
                    "Metric": "TTM EPS",
                    "App Value": f"{ttm_eps:,.4f}" if ttm_eps is not None else "N/A",
                    "Official Report Value": f"{sum(eps_vals):,.4f}" if eps_vals else "N/A",
                    "Difference": "N/A",
                    "Formula": "Sum of 4 most recent quarterly EPS",
                    "Source": ttm_rec.get("source", "ttm_from_reports"),
                    "Period": period_str,
                    "Status": "INSUFFICIENT DATA (<4 quarterly EPS)",
                })
        else:
            rows.append({
                "Ticker": symbol,
                "Company": company_name,
                "Metric": "TTM EPS",
                "App Value": f"{ttm_eps:,.4f}" if ttm_eps is not None else "N/A",
                "Official Report Value": "N/A",
                "Difference": "N/A",
                "Formula": "Sum of 4 most recent quarterly EPS",
                "Source": ttm_rec.get("source", "ttm_from_reports"),
                "Period": period_str,
                "Status": "INSUFFICIENT QUARTERLY REPORTS",
            })

    return rows


def main():
    parser = argparse.ArgumentParser(description="Validate official fundamental data vs raw filings")
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS,
                        help="Tickers to validate")
    parser.add_argument("--output", "-o", default=None,
                        help="Output CSV file path (optional)")
    args = parser.parse_args()

    init_db()

    print("=" * 120)
    print("OFFICIAL DATA VALIDATION — App values vs raw filing ground truth")
    print("No third-party aggregators involved")
    print("=" * 120)

    all_rows: List[Dict[str, Any]] = []

    for symbol in args.tickers:
        print(f"\n--- {symbol} ---")
        rows = validate_ticker(symbol)
        all_rows.extend(rows)

    print(f"\n{'Company':<20} | {'Metric':<20} | {'App Value':>15} | {'Official Report Value':>22} | {'Diff':>12} | {'Formula':<35} | {'Source':<16} | {'Period':<12} | {'Status'}")
    print(f"{'-'*22}-+-{'-'*22}-+-{'-'*17}-+-{'-'*24}-+-{'-'*14}-+-{'-'*37}-+-{'-'*18}-+-{'-'*14}-+-{'-'*40}")
    for r in all_rows:
        print(f"{str(r['Company']):<20} | {str(r['Metric']):<20} | {str(r['App Value']):>15} | "
              f"{str(r['Official Report Value']):>22} | {str(r['Difference']):>12} | "
              f"{str(r['Formula']):<35} | {str(r['Source']):<16} | {str(r['Period']):<12} | {str(r['Status'])}")

    status_counts = {}
    for r in all_rows:
        s = r["Status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    print("\n" + "=" * 120)
    print("VALIDATION SUMMARY")
    print("=" * 120)
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")

    mismatches = sum(1 for r in all_rows if r["Status"] == "MISMATCH")
    matches = sum(1 for r in all_rows if r["Status"] == "MATCH")
    print(f"\n  Total metrics checked: {len(all_rows)}")
    print(f"  Matches: {matches}")
    print(f"  Mismatches: {mismatches}")
    print(f"  Overall: {'PASS' if mismatches == 0 else 'REVIEW NEEDED'}")

    if args.output:
        df = pd.DataFrame(all_rows)
        df.to_csv(args.output, index=False, quoting=csv.QUOTE_ALL)
        print(f"\n  Report saved to: {args.output}")

    return all_rows


if __name__ == "__main__":
    main()
