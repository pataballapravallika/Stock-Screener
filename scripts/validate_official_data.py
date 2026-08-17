#!/usr/bin/env python
"""Validate official fundamental data against the raw XBRL filing ground truth.

For each ticker, this script:
  1. Reads the latest annual or quarterly record from the DB
     (``fundamental_reports``).
  2. Locates the raw XBRL filing XML on disk
     (``data/raw_filings/<TICKER>/<date>/filing.xml``).
  3. Re-parses the raw filing independently using ``lxml`` with Indian
     SEBI IN-CAPMKT taxonomy tag mappings to extract canonical metric
     values.
  4. Converts monetary values from rupees to INR crores (÷1e7).
     EPS is left in rupees per share.
  5. Compares the "App Value" (what the app stores in the DB) against the
     "Official Report Value" (re-parsed from the raw filing).
  6. Prints a table:

       Company | Metric | App Value | Official Report Value | Difference | Formula | Source | Period | Status

  7. Also validates TTM EPS (must equal the sum of 4 distinct quarterly
     EPS values — never trailing/forward-derived).

No third-party aggregators are involved at any step.

Usage:
    python scripts/validate_official_data.py [--tickers RELIANCE TCS]
                                              [--output validation_report.csv]
"""
import argparse
import csv
import json
import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.database import (
    init_db,
    get_latest_quarterly_reports,
    get_latest_annual_reports,
    get_ttm_record,
    get_company_info,
    get_raw_filing,
)
from data.raw_filing_storage import RAW_FILINGS_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("validate_official_data")

DEFAULT_TICKERS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "SBIN"]

ROPE_TO_CRORES = 10_000_000.0


# Indian XBRL tag → canonical metric name.
# Each entry maps (tag_local_name, is_eps) to canonical field.
# Monetary values are in rupees (÷1e7 → crores).
# EPS values are per-share in rupees (no conversion).
INDIAN_XBRL_TAGS: Dict[str, List[Tuple[str, bool]]] = {
    "revenue": [
        ("RevenueFromOperations", False),
        ("SegmentRevenueFromOperations", False),
        ("TotalRevenue", False),
        ("Turnover", False),
    ],
    "pat": [
        ("ProfitLossForPeriod", False),
        ("ProfitLossForThePeriod", False),
        ("ProfitLossFromOrdinaryActivitiesAfterTax", False),
        ("ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates", False),
        ("NetProfit", False),
        ("ProfitAfterTax", False),
    ],
    "ebit": [
        ("ProfitBeforeExceptionalItemsAndTax", False),
        ("ProfitBeforeTax", False),
        ("ProfitLossFromOrdinaryActivitiesBeforeTax", False),
        ("SegmentProfitBeforeTax", False),
        ("EBIT", False),
    ],
    "eps": [
        ("DilutedEarningsLossPerShareFromContinuingOperations", True),
        ("DilutedEarningsPerShareBeforeExtraordinaryItems", True),
        ("DilutedEarningsLossPerShareFromContinuingAndDiscontinuedOperations", True),
        ("DilutedEarningsPerShareAfterExtraordinaryItems", True),
        ("BasicEarningsLossPerShareFromContinuingOperations", True),
        ("BasicEarningsPerShareBeforeExtraordinaryItems", True),
        ("BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations", True),
        ("BasicEarningsPerShareAfterExtraordinaryItems", True),
    ],
    "diluted_eps": [
        ("DilutedEarningsLossPerShareFromContinuingOperations", True),
        ("DilutedEarningsPerShareBeforeExtraordinaryItems", True),
        ("DilutedEarningsLossPerShareFromContinuingAndDiscontinuedOperations", True),
        ("DilutedEarningsPerShareAfterExtraordinaryItems", True),
        ("BasicEarningsLossPerShareFromContinuingOperations", True),
        ("BasicEarningsPerShareBeforeExtraordinaryItems", True),
    ],
    "share_capital": [
        ("PaidUpValueOfEquityShareCapital", False),
        ("EquityShareCapital", False),
        ("EquityCapital", False),
    ],
    "face_value": [
        ("FaceValueOfEquityShareCapital", True),
        ("FaceValueOfEquityShares", True),
    ],
    "operating_profit": [
        ("ProfitBeforeExceptionalItemsAndTax", False),
        ("OperatingProfit", False),
        ("OperatingProfitBeforeExceptionalItemsAndTax", False),
        ("ProfitBeforeTax", False),
        ("ProfitLossFromOrdinaryActivitiesBeforeTax", False),
        ("SegmentProfitBeforeTax", False),
    ],
    "depreciation_amortization": [
        ("DepreciationDepletionAndAmortisationExpense", False),
        ("DepreciationAndAmortization", False),
    ],
    "total_assets": [
        ("SegmentAssets", False),
        ("NetSegmentAssets", False),
        ("TotalAssets", False),
        ("Assets", False),
    ],
    "total_liabilities": [
        ("SegmentLiabilities", False),
        ("NetSegmentLiabilities", False),
        ("TotalLiabilities", False),
        ("Liabilities", False),
    ],
    "interest_income": [
        ("InterestEarned", False),
        ("RevenueOnInvestments", False),
    ],
    "interest_expense": [
        ("InterestExpended", False),
        ("FinanceCosts", False),
        ("InterestExpense", False),
    ],
    "interest_on_advances": [
        ("InterestOrDiscountOnAdvancesOrBills", False),
    ],
    "interest_from_rbi": [
        ("InterestOnBalancesWithReserveBankOfIndiaAndOtherInterBankFunds", False),
    ],
    "provisions": [
        ("ProvisionsOtherThanTaxAndContingencies", False),
        ("Provisions", False),
    ],
    "gross_npa": [
        ("GrossNonPerformingAssets", False),
    ],
    "npa": [
        ("NonPerformingAssets", False),
    ],
    "gross_npa_pct": [
        ("PercentageOfGrossNpa", True),
    ],
    "npa_pct": [
        ("PercentageOfNpa", True),
    ],
    "total_income": [
        ("Income", False),
        ("TotalIncome", False),
    ],
    "operating_expenses": [
        ("OperatingExpenses", False),
    ],
    "other_interest": [
        ("OtherInterest", False),
    ],
    "segment_revenue": [
        ("SegmentRevenue", False),
    ],
    "segment_profit_before_tax": [
        ("SegmentProfitLossBeforeTaxAndFinanceCosts", False),
    ],
    "segment_finance_costs": [
        ("SegmentFinanceCosts", False),
    ],
    "unallocable_assets": [
        ("UnAllocableAssets", False),
    ],
    "unallocable_liabilities": [
        ("UnAllocableLiabilities", False),
    ],
}

# Context IDs:
#   OneD  = One duration (current quarter income statement)
#   OneI  = One instant  (current quarter balance sheet)
#   FourD = Four durations (YTD / annual income statement)
#   FourI = Four instants  (annual balance sheet)
INCOME_CONTEXTS = ("OneD", "FourD")
BALANCE_CONTEXTS = ("OneI", "FourI")


def _is_bank(company_name: str, sector: str) -> bool:
    """Determine if a company is a banking/financial institution."""
    text = f"{company_name or ''} {sector or ''}".lower()
    bank_keywords = ["bank", "financial", "finance", "hdfc", "sbi", "icici", "kotak", "yesbank"]
    return any(kw in text for kw in bank_keywords)


def _parse_indian_xbrl(file_path: str) -> Dict[str, Any]:
    """Parse an Indian SEBI IN-CAPMKT XBRL filing with lxml.

    Returns a dict of canonical metric → value.  Monetary values are
    converted to INR crores; EPS and face value are left in rupees.
    """
    result: Dict[str, Any] = {}
    if not os.path.isfile(file_path):
        return result

    try:
        parser = etree.XMLParser(recover=True, huge_tree=True)
        with open(file_path, "rb") as f:
            data = f.read()
        root = etree.fromstring(data, parser)
    except Exception as e:
        result["_parse_error"] = str(e)
        return result

    tag_to_values: Dict[str, List[Tuple[str, str]]] = {}
    for elem in root.iter():
        tag = elem.tag
        if not isinstance(tag, str) or "}" not in tag:
            continue
        local = tag.split("}")[-1]
        ctx = elem.get("contextRef", "")
        val = (elem.text or "").strip()
        if not ctx or not val or len(val) <= 1:
            continue
        tag_to_values.setdefault(local, []).append((ctx, val))

    for canonical, tag_list in INDIAN_XBRL_TAGS.items():
        for tag_name, is_eps in tag_list:
            if tag_name not in tag_to_values:
                continue
            for ctx, raw_val in tag_to_values[tag_name]:
                fval = _safe_float(raw_val)
                if fval is None:
                    continue

                if canonical in ("total_assets", "total_liabilities"):
                    if ctx not in BALANCE_CONTEXTS:
                        continue
                else:
                    if ctx not in INCOME_CONTEXTS:
                        continue

                if not is_eps and canonical not in ("face_value", "gross_npa_pct", "npa_pct",
                                                       "debt_equity", "nii", "nim"):
                    fval = fval / ROPE_TO_CRORES

                if result.get(canonical) is None:
                    result[canonical] = fval
                break

    result["_source_type"] = "nse_xbrl"
    return result


def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        s = str(val).strip().replace(",", "")
        if not s or s.lower() in ("n/a", "none", "nan", "-", "--"):
            return None
        f = float(s)
        if f != f or f == float("inf"):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _find_filing_for_date(symbol: str, report_date: str) -> Optional[str]:
    """Find the raw filing XML on disk for a given symbol and report date.

    Tries the DB raw_filings table first, then searches the disk
    directory for a matching ISO date directory.
    """
    if not report_date:
        return None

    try:
        iso_date = str(pd.to_datetime(report_date).strftime("%Y-%m-%d"))
    except Exception:
        iso_date = report_date

    ticker_dir = os.path.join(RAW_FILINGS_DIR, symbol.upper())
    if os.path.isdir(ticker_dir):
        for ext in (".xml", ".xbrl", ".html", ".htm"):
            path = os.path.join(ticker_dir, iso_date, f"filing{ext}")
            if os.path.isfile(path):
                return path
        for ext in (".xml", ".pdf"):
            path = os.path.join(ticker_dir, iso_date, f"filing{ext}")
            if os.path.isfile(path):
                return path

    meta = get_raw_filing(symbol, iso_date, None)
    if meta and meta.get("file_path"):
        fp = meta["file_path"]
        if os.path.isfile(fp):
            return fp

    if os.path.isdir(ticker_dir):
        dirs = sorted(
            [d for d in os.listdir(ticker_dir) if os.path.isdir(os.path.join(ticker_dir, d))],
            reverse=True,
        )
        iso_dirs = [d for d in dirs if re.match(r"\d{4}-\d{2}-\d{2}", d)]
        if iso_dirs:
            for ext in (".xml", ".xbrl", ".html", ".htm"):
                path = os.path.join(ticker_dir, iso_dirs[0], f"filing{ext}")
                if os.path.isfile(path):
                    return path
        else:
            for d in dirs:
                for ext in (".xml", ".pdf", ".html", ".htm"):
                    path = os.path.join(ticker_dir, d, f"filing{ext}")
                    if os.path.isfile(path):
                        return path

    return None


def _normalize_value(val: Any) -> Optional[float]:
    if val is None:
        return None
    f = _safe_float(val)
    return f


METRIC_FIELDS: List[Tuple[str, str, str, str]] = [
    ("Revenue",          "revenue",            "Revenue from Operations",                    "INR Cr"),
    ("PAT",              "pat",                "Profit after tax",                           "INR Cr"),
    ("EPS",              "eps",                "Basic EPS (₹/share)",                        "INR"),
    ("Diluted EPS",      "diluted_eps",        "Diluted EPS (₹/share)",                      "INR"),
    ("EBIT",             "ebit",               "Profit Before Tax",                          "INR Cr"),
    ("Operating Profit",   "operating_profit",   "Operating Profit / EBIT",                    "INR Cr"),
    ("Share Capital",    "share_capital",      "Paid-up Equity Share Capital",               "INR Cr"),
    ("Face Value",       "face_value",         "Face Value per Share",                       "INR"),
    ("Depreciation",     "depreciation_amortization", "Depreciation & Amortisation",        "INR Cr"),
    ("Total Assets",     "total_assets",       "Total Assets (balance sheet)",             "INR Cr"),
    ("Total Liabilities", "total_liabilities", "Total Liabilities (balance sheet)",         "INR Cr"),
]

BANK_METRIC_FIELDS: List[Tuple[str, str, str, str]] = METRIC_FIELDS + [
    ("Interest Earned",    "interest_income",       "Interest Earned",                     "INR Cr"),
    ("Interest Expense",   "interest_expense",      "Interest Expended",                   "INR Cr"),
    ("Interest on Advances", "interest_on_advances", "Interest on Advances/Bills",         "INR Cr"),
    ("Interest from RBI",  "interest_from_rbi",     "Interest on RBI balances",             "INR Cr"),
    ("Other Interest",     "other_interest",        "Other Interest Income",               "INR Cr"),
    ("Provisions",         "provisions",            "Provisions (excluding tax)",           "INR Cr"),
    ("Gross NPA",          "gross_npa",             "Gross Non-Performing Assets",          "INR Cr"),
    ("Gross NPA %",        "gross_npa_pct",         "Gross NPA as % of Advances",           "%"),
    ("NPA",                "npa",                   "Net Non-Performing Assets",            "INR Cr"),
    ("NPA %",              "npa_pct",               "Net NPA as % of Advances",             "%"),
    ("Total Income",       "total_income",          "Total Income (Interest + Other)",   "INR Cr"),
    ("Operating Expenses", "operating_expenses",    "Operating Expenses",                   "INR Cr"),
    ("Segment Revenue",    "segment_revenue",       "Total Segment Revenue",                "INR Cr"),
    ("Unalloc. Assets",    "unallocable_assets",    "Unallocated Assets",                   "INR Cr"),
    ("Unalloc. Liabilities", "unallocable_liabilities", "Unallocated Liabilities",          "INR Cr"),
]


def validate_ticker(symbol: str) -> List[Dict[str, Any]]:
    """Produce validation rows for a single ticker."""
    rows: List[Dict[str, Any]] = []

    company_info = get_company_info(symbol)
    company_name = company_info.get("company_name") or symbol
    sector = company_info.get("sector") or "N/A"
    is_bank = _is_bank(company_name, sector)

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
            "Ticker": symbol, "Company": company_name, "Metric": "ALL",
            "App Value": "N/A", "Official Report Value": "N/A", "Difference": "N/A",
            "Formula": "N/A", "Source": "N/A", "Period": "N/A",
            "Status": "NOT VERIFIED — no data in DB",
        })
        return rows

    if q_num and fy:
        period_str = f"Q{q_num} FY{fy}"
    elif fy:
        period_str = f"FY{fy}"
    else:
        period_str = period_type or "N/A"

    filing_path = _find_filing_for_date(symbol, report_date)
    source_url = db_rec.get("source_url") or "N/A"
    source_type = db_rec.get("source_type") or db_rec.get("source") or "N/A"

    if filing_path and filing_path.lower().endswith((".xml", ".xbrl", ".html", ".htm")):
        raw = _parse_indian_xbrl(filing_path)
    else:
        raw = {}

    fields = BANK_METRIC_FIELDS if is_bank else METRIC_FIELDS

    for display_name, db_field, formula, unit in fields:
        app_val = _normalize_value(db_rec.get(db_field))
        raw_val = _normalize_value(
            raw.get(db_field) or raw.get(db_field.replace("_", ""))
        )

        if app_val is not None and raw_val is not None:
            if unit == "INR":
                threshold = 0.001
            elif unit == "%":
                threshold = 0.01
            else:
                threshold = max(abs(raw_val) * 0.005, 0.01)
            diff = app_val - raw_val
            if abs(diff) <= threshold:
                status = "MATCH"
            else:
                status = "MISMATCH"
            diff_str = f"{diff:+.4f}"
        elif app_val is not None and raw_val is None:
            status = "APP_HAS_VALUE (raw filing metric not found)"
            diff_str = "N/A"
        elif app_val is None and raw_val is not None:
            status = "MISSING IN DB"
            diff_str = "N/A"
        else:
            status = "N/A"
            diff_str = "N/A"

        app_str = f"{app_val:,.4f}" if app_val is not None else "N/A"
        raw_str = f"{raw_val:,.4f}" if raw_val is not None else "N/A"

        rows.append({
            "Ticker": symbol,
            "Company": company_name,
            "Metric": display_name,
            "App Value": app_str,
            "Official Report Value": raw_str,
            "Difference": diff_str,
            "Formula": formula,
            "Source": source_type,
            "Report URL": source_url,
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
                    "Formula": "Sum of 4 distinct quarterly EPS",
                    "Source": ttm_rec.get("source", "ttm_from_reports"),
                    "Period": period_str,
                    "Status": ttm_status,
                })
            else:
                rows.append({
                    "Ticker": symbol, "Company": company_name,
                    "Metric": "TTM EPS",
                    "App Value": f"{ttm_eps:,.4f}" if ttm_eps is not None else "N/A",
                    "Official Report Value": "N/A", "Difference": "N/A",
                    "Formula": "Sum of 4 distinct quarterly EPS",
                    "Source": ttm_rec.get("source", "ttm_from_reports"),
                    "Period": period_str, "Status": "INSUFFICIENT DATA (<4 quarterly EPS)",
                })
        else:
            rows.append({
                "Ticker": symbol, "Company": company_name,
                "Metric": "TTM EPS",
                "App Value": f"{ttm_eps:,.4f}" if ttm_eps is not None else "N/A",
                "Official Report Value": "N/A", "Difference": "N/A",
                "Formula": "Sum of 4 distinct quarterly EPS",
                "Source": ttm_rec.get("source", "ttm_from_reports"),
                "Period": period_str, "Status": "INSUFFICIENT QUARTERLY REPORTS",
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
    print("OFFICIAL DATA VALIDATION")
    print(f"Companies: {args.tickers}")
    print("App values (DB) vs official report values (re-parsed raw XBRL)")
    print("=" * 120)

    all_rows: List[Dict[str, Any]] = []

    for symbol in args.tickers:
        clean = symbol.strip().upper()
        for suffix in (".NS", ".BO"):
            if clean.endswith(suffix):
                clean = clean[:-len(suffix)]
                break
        print(f"\n--- {clean} ---")
        rows = validate_ticker(clean)
        all_rows.extend(rows)

    print(f"\n{'Company':<20} | {'Metric':<18} | {'App Value':>14} | {'Official Report Value':>22} | {'Diff':>10} | {'Source':<12} | {'Period':<12} | {'Status'}")
    print(f"{'-'*22}-+-{'-'*20}-+-{'-'*16}-+-{'-'*24}-+-{'-'*12}-+-{'-'*14}-+-{'-'*14}-+-{'-'*40}")
    for r in all_rows:
        print(f"{str(r['Company']):<20} | {str(r['Metric']):<18} | {str(r['App Value']):>14} | "
              f"{str(r['Official Report Value']):>22} | {str(r['Difference']):>10} | "
              f"{str(r['Source']):<12} | {str(r['Period']):<12} | {str(r['Status'])}")

    status_counts: Dict[str, int] = {}
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
    print(f"\n  Total rows: {len(all_rows)}")
    print(f"  Matches: {matches}")
    print(f"  Mismatches: {mismatches}")
    print(f"\n  Result: {'PASS — all comparable metrics match' if mismatches == 0 else 'REVIEW NEEDED — mismatches detected'}")

    if args.output:
        df = pd.DataFrame(all_rows)
        df.to_csv(args.output, index=False, quoting=csv.QUOTE_ALL)
        print(f"\n  Report saved to: {args.output}")

    critical_metrics = ["Revenue", "PAT", "EPS", "TTM EPS"]
    print("\n--- Critical Metrics Check ---")
    for t in args.tickers:
        clean = t.strip().upper()
        for suffix in (".NS", ".BO"):
            if clean.endswith(suffix):
                clean = clean[:-len(suffix)]
                break
        ticker_rows = [r for r in all_rows if r["Ticker"] == clean]
        for cm in critical_metrics:
            row = next((r for r in ticker_rows if r["Metric"] == cm), None)
            if row:
                val = row["App Value"] if row["App Value"] != "N/A" else row["Official Report Value"]
                status_icon = "OK" if row["Status"] in ("MATCH",) else "WARN" if row["Status"].startswith("APP_HAS_VALUE") else "FAIL"
                print(f"  [{status_icon}] {clean} {cm}: {val} ({row['Status']})")
            else:
                print(f"  [FAIL] {clean} {cm}: not found in validation output")

    return all_rows


if __name__ == "__main__":
    main()
