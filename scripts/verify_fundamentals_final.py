"""
Verification script for the fundamental data layer.

Tests five Indian equities:
  RELIANCE.NS, TCS.NS, INFY.NS, HDFCBANK.NS, SBIN.NS

For each ticker, produces a report containing:
  - data source
  - extracted values (latest quarterly and annual)
  - calculated values (ratios, TTM, growth, Piotroski, Altman)
  - validation status (extracted vs calculated, 5% threshold)
  - missing values

Results are printed to stdout and saved to reports/verification_report_<timestamp>.json
"""

import json
import sys
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ── path setup ──────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

from data.providers.official_reports_provider import OfficialReportsProvider
from data.providers.xbrl_provider import XBRLProvider
from data.providers.yahoo_price_provider import YahooPriceProvider
from data.providers.base_provider import BaseFundamentalProvider
from data.calculations.financial_calculator import FinancialCalculator
from data.calculations.validation import ValidationEngine
from data.database import (
    init_db,
    get_latest_quarterly_reports,
    get_latest_annual_reports,
    get_ttm_record,
    get_company_info,
    get_validation_reports,
)
from data.fetch_fundamentals import fetch_fundamentals


TICKERS = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "SBIN.NS"]

REPORT_DIR = os.path.join(PROJECT_ROOT, "reports")
os.makedirs(REPORT_DIR, exist_ok=True)


def _safe(v) -> Optional[float]:
    return FinancialCalculator._safe(v)


def _fmt(v) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def build_record_from_db(ticker: str, period: str, row: Dict[str, Any]) -> Dict[str, Any]:
    """Build a normalized record dict from a DB row."""
    return {
        "ticker": ticker,
        "period": period,
        "report_date": row.get("report_date"),
        "financial_year": row.get("financial_year"),
        "quarter": row.get("quarter"),
        "revenue": row.get("revenue"),
        "operating_profit": row.get("operating_profit"),
        "ebit": row.get("ebit"),
        "pat": row.get("pat"),
        "eps": row.get("eps"),
        "assets": row.get("assets"),
        "current_assets": row.get("current_assets"),
        "liabilities": row.get("liabilities"),
        "current_liabilities": row.get("current_liabilities"),
        "equity": row.get("equity"),
        "debt": row.get("debt"),
        "operating_cash_flow": row.get("operating_cash_flow"),
        "capex": row.get("capex"),
        "gross_profit": row.get("gross_profit"),
        "retained_earnings": row.get("retained_earnings"),
        "source": row.get("source"),
    }


def check_missing(record: Dict[str, Any]) -> List[str]:
    required_fields = [
        "revenue", "operating_profit", "ebit", "pat", "eps",
        "assets", "current_assets", "liabilities", "current_liabilities",
        "equity", "debt", "operating_cash_flow", "capex",
    ]
    return [f for f in required_fields if record.get(f) is None]


def ratio_row(label: str, extracted: Any, calculated: Any) -> Dict[str, Any]:
    e = _safe(extracted)
    c = _safe(calculated)
    if e is None and c is None:
        diff_pct = None
        status = "MISSING"
    elif e is None or c is None:
        diff_pct = None
        status = "MISSING"
    else:
        denom = max(abs(e), abs(c))
        diff_pct = abs(e - c) / denom * 100 if denom != 0 else 0.0
        status = "OK" if diff_pct <= 5.0 else "MISMATCH"
    return {
        "metric": label,
        "extracted": _fmt(extracted),
        "calculated": _fmt(calculated),
        "diff_pct": round(diff_pct, 2) if diff_pct is not None else None,
        "status": status,
    }


def validate_record_full(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    ratios = FinancialCalculator.compute_all_ratios(record)
    rows = [
        ratio_row("ROE",             record.get("roe"),             ratios.get("roe")),
        ratio_row("ROA",             record.get("roa"),             ratios.get("roa")),
        ratio_row("ROCE",            record.get("roce"),            ratios.get("roce")),
        ratio_row("Debt/Equity",     record.get("debt_equity"),     ratios.get("debt_equity")),
        ratio_row("OPM",             record.get("opm"),             ratios.get("opm")),
        ratio_row("NPM",             record.get("npm"),             ratios.get("npm")),
        ratio_row("Gross Margin",    record.get("gross_margin"),    ratios.get("gross_margin")),
        ratio_row("Working Capital", record.get("working_capital"), ratios.get("working_capital")),
    ]
    fcf_calc = FinancialCalculator.compute_fcf(
        record.get("operating_cash_flow"), record.get("capex")
    )
    rows.append(ratio_row("FreeCashFlow", record.get("fcf"), fcf_calc))
    return rows


def period_label(row: Dict[str, Any]) -> str:
    fy = row.get("financial_year")
    q = row.get("quarter")
    if q:
        return f"FY{fy} Q{q}"
    return f"FY{fy}"


def run_verification(tickers: List[str], use_cache: bool = True) -> Dict[str, Any]:
    init_db()
    provider = OfficialReportsProvider()
    calculator = FinancialCalculator()
    val_engine = ValidationEngine(threshold=0.05)
    price_provider = YahooPriceProvider()

    all_reports: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold_pct": 5.0,
        "tickers": [],
    }

    for ticker in tickers:
        print(f"\n{'='*70}")
        print(f"TICKER: {ticker}")
        print(f"{'='*70}")

        t0 = time.time()
        try:
            fund = fetch_fundamentals(ticker)
        except Exception as e:
            print(f"  ERROR fetching fundamentals: {e}")
            all_reports["tickers"].append({
                "ticker": ticker,
                "status": "ERROR",
                "error": str(e),
            })
            continue
        elapsed = time.time() - t0

        if not fund:
            print(f"  No fundamental data returned ({elapsed:.1f}s)")
            all_reports["tickers"].append({
                "ticker": ticker,
                "status": "NO_DATA",
                "elapsed_seconds": round(elapsed, 2),
            })
            continue

        source = fund.get("fundamentals_source", "unknown")
        print(f"  Source:          {source}")
        print(f"  Fetch time:      {elapsed:.1f}s")

        # ── DB state ─────────────────────────────────────────────────────────
        q_df = get_latest_quarterly_reports(ticker, n=4)
        a_df = get_latest_annual_reports(ticker, n=3)
        ttm_rec = get_ttm_record(ticker, "ttm")
        company_info = get_company_info(ticker)

        q_records = q_df.to_dict("records") if not q_df.empty else []
        a_records = a_df.to_dict("records") if not a_df.empty else []

        # ── Quarterly section ────────────────────────────────────────────────
        quarterly_section = []
        for rec in q_records:
            db_rec = build_record_from_db(ticker, "quarterly", rec)
            missing = check_missing(db_rec)
            rows = validate_record_full(db_rec)
            mismatches = [r for r in rows if r["status"] == "MISMATCH"]
            quarterly_section.append({
                "period": db_rec.get("report_date"),
                "financial_year": db_rec.get("financial_year"),
                "quarter": db_rec.get("quarter"),
                "label": period_label(db_rec),
                "missing_fields": missing,
                "validation": rows,
                "mismatch_count": len(mismatches),
            })

        # ── Annual section ───────────────────────────────────────────────────
        annual_section = []
        for rec in a_records:
            db_rec = build_record_from_db(ticker, "annual", rec)
            missing = check_missing(db_rec)
            rows = validate_record_full(db_rec)
            mismatches = [r for r in rows if r["status"] == "MISMATCH"]
            annual_section.append({
                "period": db_rec.get("report_date"),
                "financial_year": db_rec.get("financial_year"),
                "label": period_label(db_rec),
                "missing_fields": missing,
                "validation": rows,
                "mismatch_count": len(mismatches),
            })

        # ── TTM section ──────────────────────────────────────────────────────
        ttm_section = []
        if ttm_rec:
            ttm_db = build_record_from_db(ticker, "ttm", ttm_rec)
            missing = check_missing(ttm_db)
            rows = validate_record_full(ttm_db)
            mismatches = [r for r in rows if r["status"] == "MISMATCH"]
            ttm_section.append({
                "period": "TTM",
                "financial_year": ttm_db.get("financial_year"),
                "label": f"TTM (FY{ttm_db.get('financial_year')})",
                "missing_fields": missing,
                "validation": rows,
                "mismatch_count": len(mismatches),
            })

        # ── Computed scores ──────────────────────────────────────────────────
        piotroski = fund.get("piotroski_f_score", {})
        altman = fund.get("altman_z_score", {})

        # ── Growth ───────────────────────────────────────────────────────────
        q_growth = fund.get("quarterly_growth", {})
        a_growth = fund.get("annual_growth", {})

        # ── Top-level metrics ────────────────────────────────────────────────
        top_metrics = {
            "MarketCap": fund.get("MarketCap"),
            "PE": fund.get("PE"),
            "PEG": fund.get("PEG"),
            "ROE": fund.get("ROE"),
            "ROCE": fund.get("ROCE"),
            "ROA": fund.get("ROA"),
            "DebtEquity": fund.get("DebtEquity"),
            "ProfitMargin": fund.get("ProfitMargin"),
            "GrossMargin": fund.get("GrossMargin"),
            "RevenueGrowth_annual": a_growth.get("revenue_growth"),
            "PATGrowth_annual": a_growth.get("pat_growth"),
            "EPSGrowth_annual": a_growth.get("eps_growth"),
            "EPSYoY_quarterly": q_growth.get("eps_yoy"),
            "EPSQoQ_quarterly": q_growth.get("eps_qoq"),
            "SalesYoY_quarterly": q_growth.get("sales_yoy"),
            "SalesQoQ_quarterly": q_growth.get("sales_qoq"),
            "PATYoY_quarterly": q_growth.get("pat_yoy"),
            "PATQoQ_quarterly": q_growth.get("pat_qoq"),
            "PiotroskiScore": piotroski.get("score"),
            "PiotroskiMax": piotroski.get("max_score"),
            "AltmanZ": altman.get("value"),
            "AltmanStatus": altman.get("status"),
            "FreeCashFlowTTM": fund.get("FreeCashFlowTTM"),
            "FreeCashFlowAnnual": fund.get("FreeCashFlowAnnual"),
            "OperatingCashFlowTTM": fund.get("OperatingCashFlowTTM"),
        }

        # ── Console output ───────────────────────────────────────────────────
        print(f"\n  --- Top-level metrics ---")
        for k, v in top_metrics.items():
            print(f"    {k:30s}: {_fmt(v)}")

        print(f"\n  --- Quarterly validation ---")
        for sec in quarterly_section:
            print(f"    [{sec['label']}] missing={sec['missing_fields'] or 'none'}")
            for r in sec["validation"]:
                marker = "OK" if r["status"] == "OK" else ("MISMATCH" if r["status"] == "MISMATCH" else "MISSING")
                print(f"      [{marker:9s}] {r['metric']:20s} ext={r['extracted']:>12s} calc={r['calculated']:>12s}  diff={r['diff_pct'] if r['diff_pct'] is not None else 'N/A':>8s}%")

        print(f"\n  --- Annual validation ---")
        for sec in annual_section:
            print(f"    [{sec['label']}] missing={sec['missing_fields'] or 'none'}")
            for r in sec["validation"]:
                marker = "OK" if r["status"] == "OK" else ("MISMATCH" if r["status"] == "MISMATCH" else "MISSING")
                print(f"      [{marker:9s}] {r['metric']:20s} ext={r['extracted']:>12s} calc={r['calculated']:>12s}  diff={r['diff_pct'] if r['diff_pct'] is not None else 'N/A':>8s}%")

        if ttm_section:
            print(f"\n  --- TTM validation ---")
            for sec in ttm_section:
                print(f"    [{sec['label']}] missing={sec['missing_fields'] or 'none'}")
                for r in sec["validation"]:
                    marker = "OK" if r["status"] == "OK" else ("MISMATCH" if r["status"] == "MISMATCH" else "MISSING")
                    print(f"      [{marker:9s}] {r['metric']:20s} ext={r['extracted']:>12s} calc={r['calculated']:>12s}  diff={r['diff_pct'] if r['diff_pct'] is not None else 'N/A':>8s}%")

        total_mismatches = (
            sum(s["mismatch_count"] for s in quarterly_section)
            + sum(s["mismatch_count"] for s in annual_section)
            + sum(s["mismatch_count"] for s in ttm_section)
        )
        all_missing = []
        for s in quarterly_section + annual_section + ttm_section:
            all_missing.extend(s["missing_fields"])

        ticker_report = {
            "ticker": ticker,
            "status": "OK" if total_mismatches == 0 else "MISMATCHES_FOUND",
            "source": source,
            "elapsed_seconds": round(elapsed, 2),
            "company_name": company_info.get("company_name"),
            "sector": company_info.get("sector"),
            "industry": company_info.get("industry"),
            "top_metrics": {k: _safe(v) for k, v in top_metrics.items()},
            "quarterly": quarterly_section,
            "annual": annual_section,
            "ttm": ttm_section,
            "piotroski_f_score": piotroski,
            "altman_z_score": altman,
            "total_mismatches": total_mismatches,
            "all_missing_fields": list(set(all_missing)),
        }

        all_reports["tickers"].append(ticker_report)

    return all_reports


def main():
    print("="*70)
    print("FUNDAMENTAL DATA LAYER VERIFICATION")
    print(f"Tickers: {', '.join(TICKERS)}")
    print(f"Threshold: 5%")
    print("="*70)

    report = run_verification(TICKERS)

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("OVERALL SUMMARY")
    print(f"{'='*70}")

    total_ticks = 0
    total_ok = 0
    total_mismatches = 0
    total_missing_vals = 0

    for tr in report["tickers"]:
        if tr.get("status") == "ERROR":
            print(f"  {tr['ticker']:15s}: ERROR - {tr.get('error', 'unknown')}")
            continue
        if tr.get("status") == "NO_DATA":
            print(f"  {tr['ticker']:15s}: NO DATA ({tr.get('elapsed_seconds', 0):.1f}s)")
            continue

        mismatches = tr.get("total_mismatches", 0)
        missing = len(tr.get("all_missing_fields", []))
        total_ticks += 1
        total_mismatches += mismatches
        total_missing_vals += missing
        status_icon = "PASS" if mismatches == 0 else "FAIL"
        print(f"  {status_icon} {tr['ticker']:15s}: {mismatches:3d} mismatches, {missing:2d} missing fields, source={tr.get('source', '?')}")

        if mismatches == 0:
            total_ok += 1

    print(f"\n  Passed:   {total_ok}/{total_ticks}")
    print(f"  Total mismatches:  {total_mismatches}")
    print(f"  Total missing val: {total_missing_vals}")

    # ── Save report ──────────────────────────────────────────────────────────
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = os.path.join(REPORT_DIR, f"verification_report_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Report saved: {path}")

    return report


if __name__ == "__main__":
    main()
