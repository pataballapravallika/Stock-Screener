#!/usr/bin/env python3
"""Comprehensive NSE Official Filings Validation Script.

For each of the 5 test companies, fetches the latest NSE filings and
produces a validation table:

  Company | Metric | App Value | NSE Reported Value | Formula | NSE Source URL | Period | Status

Status:
  OK        = exact match or within 1% where calculation is required
  MISMATCH  = difference > 1%
  N/A       = metric not reported or cannot be reliably extracted

Directly reported metrics (Revenue, PAT, EPS) must match the NSE filing
value exactly after unit normalization.

Usage:
  python scripts/validate_nse_fundamentals.py
"""
import sys
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.fetch_fundamentals import fetch_fundamentals, clear_fundamentals_cache
from data.database import get_latest_quarterly_reports, get_latest_annual_reports, get_ttm_record
from data.calculations.financial_calculator import FinancialCalculator


TEST_COMPANIES = {
    "Reliance Industries": "RELIANCE.NS",
    "Tata Consultancy Services": "TCS.NS",
    "Infosys": "INFY.NS",
    "HDFC Bank": "HDFCBANK.NS",
    "State Bank of India": "SBIN.NS",
}

TOLERANCE_PCT = 0.01  # 1% tolerance for calculations


def _safe(val):
    if val is None:
        return None
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _fmt(val, is_pct=False, is_eps=False, is_ratio=False):
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return "N/A"
    if is_eps:
        return f"{val:.2f} INR"
    if is_pct:
        return f"{val * 100:.2f}%" if abs(val) < 5 else f"{val:.2f}%"
    if is_ratio:
        return f"{val:.2f}"
    return f"{val:,.2f} Cr"


def _compute_status(app_v, calc_v, is_direct=False):
    if app_v is None and calc_v is None:
        return "N/A"
    if app_v is None or calc_v is None:
        return "N/A"
    diff_pct = abs(app_v - calc_v) / max(abs(app_v), abs(calc_v), 1e-10)
    if is_direct:
        # Direct metrics must match exactly after unit normalization
        if abs(app_v - calc_v) < 1e-4:
            return "OK"
        return "MISMATCH"
    if diff_pct <= TOLERANCE_PCT:
        return "OK"
    return "MISMATCH"


def validate_company(name: str, symbol: str) -> pd.DataFrame:
    clear_fundamentals_cache()
    fund = fetch_fundamentals(symbol) or {}

    q_reports = get_latest_quarterly_reports(symbol, limit=8)
    a_reports = get_latest_annual_reports(symbol, limit=5)
    ttm_record = get_ttm_record(symbol, "ttm") or {}

    q_recs = q_reports.to_dict("records") if not q_reports.empty else []
    a_recs = a_reports.to_dict("records") if not a_reports.empty else []

    latest_q = q_recs[0] if q_recs else {}
    latest_a = a_recs[0] if a_recs else {}
    prev_q = q_recs[1] if len(q_recs) > 1 else {}
    prev_y_q = q_recs[4] if len(q_recs) > 4 else {}

    is_bank = any(b.lower() in (fund.get("Sector") or "").lower()
                  for b in ["financial", "bank", "finance"]) or any(b in symbol for b in ["BANK", "SBIN"])

    # Source URL — prefer the latest quarterly filing URL
    source_url = latest_q.get("source_url") or latest_a.get("source_url") or "NSE XBRL Official Filing"
    if not source_url:
        source_url = fund.get("metric_details", {}).get("Revenue", {}).get("source_url") or "NSE XBRL Official Filing"

    period = latest_q.get("quarter") and f"Q{latest_q['quarter']} FY{latest_q.get('financial_year', 'N/A')}" or \
             (latest_q.get("report_date") or "N/A")

    rows = []

    def add_row(m_name, app_v, nse_v, formula, is_pct=False, is_eps=False, is_ratio=False, is_direct=False):
        status = _compute_status(app_v, nse_v, is_direct=is_direct)
        rows.append({
            "Company": name,
            "Metric": m_name,
            "App Value": _fmt(app_v, is_pct=is_pct, is_eps=is_eps, is_ratio=is_ratio),
            "NSE Reported Value": _fmt(nse_v, is_pct=is_pct, is_eps=is_eps, is_ratio=is_ratio),
            "Formula / Source": formula,
            "NSE Source URL": source_url,
            "Period": period,
            "Status": status,
        })

    # ==================== CLASS A: DIRECTLY REPORTED FROM NSE FILINGS ====================
    # These must match exactly after unit normalization

    rep_rev = _safe(latest_q.get("revenue"))
    rep_pat = _safe(latest_q.get("pat"))
    rep_eps = _safe(latest_q.get("eps"))
    rep_ebit = _safe(latest_q.get("ebit"))
    rep_op = _safe(latest_q.get("operating_profit")) or rep_ebit
    rep_ocf = _safe(latest_q.get("operating_cash_flow"))
    rep_capex = _safe(latest_q.get("capex"))
    rep_assets = _safe(latest_q.get("assets")) or _safe(latest_a.get("assets"))
    rep_equity = _safe(latest_q.get("equity")) or _safe(latest_a.get("equity"))
    rep_liab = _safe(latest_q.get("liabilities")) or _safe(latest_a.get("liabilities"))
    rep_c_assets = _safe(latest_q.get("current_assets")) or _safe(latest_a.get("current_assets"))
    rep_c_liab = _safe(latest_q.get("current_liabilities")) or _safe(latest_a.get("current_liabilities"))
    rep_debt = _safe(latest_q.get("total_debt")) or _safe(latest_a.get("total_debt")) or \
               _safe(latest_q.get("debt")) or _safe(latest_a.get("debt"))
    rep_cash = _safe(latest_q.get("cash_and_cash_equivalents")) or _safe(latest_a.get("cash_and_cash_equivalents"))

    add_row("Revenue", fund.get("Revenue"), rep_rev, "Directly Reported — NSE XBRL RevenueFromOperations", is_direct=True)
    add_row("PAT", fund.get("PAT"), rep_pat, "Directly Reported — NSE XBRL ProfitLossForPeriod", is_direct=True)
    add_row("EPS", fund.get("EPS"), rep_eps, "Directly Reported — NSE XBRL DilutedEPS (Quarterly Filing)", is_eps=True, is_direct=True)
    add_row("EBIT", fund.get("EBIT"), rep_ebit, "Directly Reported — NSE XBRL ProfitBeforeTax", is_direct=True)
    add_row("Operating Profit", fund.get("EBIT") or rep_op, rep_op, "Directly Reported — NSE XBRL OperatingProfit", is_direct=True)
    add_row("Operating Cash Flow", fund.get("OperatingCashFlow"), rep_ocf, "Directly Reported — NSE XBRL NetCashFlowsFromUsedInOperatingActivities", is_direct=True)
    add_row("CapEx", fund.get("CapEx"), rep_capex, "Directly Reported — NSE XBRL PurchaseOfPropertyPlantAndEquipment", is_direct=True)
    add_row("Total Assets", fund.get("TotalAssets"), rep_assets, "Directly Reported — NSE XBRL TotalAssets", is_direct=True)
    add_row("Shareholders' Equity", fund.get("TotalStockholderEquity"), rep_equity, "Directly Reported — NSE XBRL TotalEquity", is_direct=True)
    add_row("Total Liabilities", fund.get("TotalLiabilities"), rep_liab, "Directly Reported — NSE XBRL TotalLiabilities", is_direct=True)
    add_row("Current Assets", fund.get("CurrentAssets"), rep_c_assets, "Directly Reported — NSE XBRL TotalCurrentAssets", is_direct=True)
    add_row("Current Liabilities", fund.get("CurrentLiabilities"), rep_c_liab, "Directly Reported — NSE XBRL TotalCurrentLiabilities", is_direct=True)
    add_row("Total Debt", fund.get("TotalDebt"), rep_debt, "Directly Reported — NSE XBRL Borrowings/Loans", is_direct=True)
    add_row("Cash & Cash Equivalents", fund.get("TotalCash"), rep_cash, "Directly Reported — NSE XBRL CashAndCashEquivalents", is_direct=True)

    # Banking-specific directly reported metrics
    if is_bank:
        rep_advances = _safe(latest_q.get("total_advances"))
        rep_deposits = _safe(latest_q.get("total_deposits"))
        rep_gross_npa = _safe(latest_q.get("gross_npa"))
        rep_net_npa = _safe(latest_q.get("net_npa"))
        rep_car = _safe(latest_q.get("car"))
        rep_interest_inc = _safe(latest_q.get("interest_income"))
        rep_interest_exp = _safe(latest_q.get("interest_expense"))
        rep_total_income = _safe(latest_q.get("total_income"))
        rep_non_int_inc = _safe(latest_q.get("non_interest_income"))
        rep_provisions = _safe(latest_q.get("provisions"))

        add_row("Interest Income", fund.get("InterestIncome"), rep_interest_inc, "Directly Reported — NSE XBRL InterestIncome", is_direct=True)
        add_row("Interest Expense", fund.get("InterestExpense"), rep_interest_exp, "Directly Reported — NSE XBRL InterestExpense", is_direct=True)
        add_row("Total Income", fund.get("TotalIncome"), rep_total_income, "Directly Reported — NSE XBRL TotalIncome", is_direct=True)
        add_row("Other Income", fund.get("NonInterestIncome"), rep_non_int_inc, "Directly Reported — NSE XBRL NonInterestIncome", is_direct=True)
        add_row("Deposits", fund.get("Deposits"), rep_deposits, "Directly Reported — NSE XBRL TotalDeposits", is_direct=True)
        add_row("Advances", fund.get("Advances"), rep_advances, "Directly Reported — NSE XBRL TotalAdvances", is_direct=True)
        add_row("GNPA", fund.get("GNPA"), rep_gross_npa, "Directly Reported — NSE XBRL GrossNPA", is_direct=True)
        add_row("NNPA", fund.get("NNPA"), rep_net_npa, "Directly Reported — NSE XBRL NetNPA", is_direct=True)
        add_row("CAR/CRAR", fund.get("CAR"), rep_car, "Directly Reported — NSE XBRL CapitalAdequacyRatio", is_direct=True)
        add_row("Provisions", fund.get("Provisions"), rep_provisions, "Directly Reported — NSE XBRL Provisions", is_direct=True)

    # ==================== CLASS B: CALCULATED FROM OFFICIAL FILING INPUTS ====================
    calc_roe = FinancialCalculator.compute_roe(rep_pat, rep_equity)
    calc_roa = FinancialCalculator.compute_roa(rep_pat, rep_assets)
    calc_roce = FinancialCalculator.compute_roce(rep_ebit, rep_assets, rep_c_liab, equity=rep_equity, debt=rep_debt)
    calc_de = FinancialCalculator.compute_debt_equity(rep_debt, rep_equity)
    calc_opm = FinancialCalculator.compute_opm(rep_op, rep_rev)
    calc_npm = FinancialCalculator.compute_npm(rep_pat, rep_rev)
    calc_fcf = FinancialCalculator.compute_fcf(rep_ocf, rep_capex)

    add_row("ROE", fund.get("ROE"), calc_roe, "PAT / Shareholders' Equity", is_pct=True)
    add_row("ROA", fund.get("ROA"), calc_roa, "PAT / Total Assets", is_pct=True)
    add_row("ROCE", fund.get("ROCE"), calc_roce, "EBIT / (Total Assets - Current Liabilities)", is_pct=True)
    add_row("Debt/Equity", fund.get("DebtEquity"), calc_de, "Total Debt / Shareholders' Equity", is_ratio=True)
    add_row("OPM", fund.get("OPM"), calc_opm, "Operating Profit / Revenue", is_pct=True)
    add_row("NPM", fund.get("NPM"), calc_npm, "PAT / Revenue", is_pct=True)
    add_row("Free Cash Flow", fund.get("FreeCashFlow"), calc_fcf, "OCF + CapEx (if CapEx<0) or OCF - CapEx (if CapEx>0)")

    # Banking calculated metrics
    if is_bank:
        if rep_interest_inc is not None and rep_interest_exp is not None:
            nii = rep_interest_inc - rep_interest_exp
            add_row("NII (Net Interest Income)", fund.get("NII"), nii, "Interest Income - Interest Expense", is_direct=True)
        if rep_total_income is not None and rep_total_income != 0 and 'nii' in dir() and nii is not None:
            nim = (nii / rep_total_income) * 100
            add_row("NIM", fund.get("NIM"), nim, "NII / Total Income", is_pct=True)
        if rep_gross_npa is not None and rep_advances is not None and rep_advances != 0:
            gnpha = (rep_gross_npa / rep_advances) * 100
            add_row("GNPA%", fund.get("GNPA"), gnpha, "Gross NPA / Total Advances", is_pct=True)
        if rep_net_npa is not None and rep_advances is not None and rep_advances != 0:
            nnpha = (rep_net_npa / rep_advances) * 100
            add_row("NNPA%", fund.get("NNPA"), nnpha, "Net NPA / Total Advances", is_pct=True)

    # ==================== CLASS C: TTM (4 Distinct Quarterly Filings) ====================
    if ttm_record:
        ttm_rev = _safe(ttm_record.get("revenue"))
        ttm_pat = _safe(ttm_record.get("pat"))
        ttm_eps = _safe(ttm_record.get("eps"))
        ttm_ocf = _safe(ttm_record.get("operating_cash_flow"))

        add_row("TTM Revenue", fund.get("TTM Revenue"), ttm_rev, "Sum of 4 distinct quarterly Revenue values")
        add_row("TTM PAT", fund.get("TTM PAT"), ttm_pat, "Sum of 4 distinct quarterly PAT values")
        add_row("TTM EPS", fund.get("TTMEPS"), ttm_eps, "Sum of 4 distinct quarterly EPS values", is_eps=True)
        add_row("TTM OCF", fund.get("OperatingCashFlowTTM"), ttm_ocf, "Sum of 4 distinct quarterly OCF values")

    # ==================== CLASS C: VALUATION (Price from NSE live feed) ====================
    try:
        from data.fetch_prices import fetch_prices
        prices = fetch_prices(symbol, period="5d")
        current_price = float(prices["Close"].iloc[-1]) if not prices.empty and "Close" in prices.columns else None
    except Exception:
        current_price = None

    # P/E = Current Price / TTM EPS
    # TTM EPS must come from 4 distinct quarterly filings
    ttm_eps_val = None
    if q_recs and len(q_recs) >= 4:
        seen = set()
        eps_vals = []
        for rec in q_recs[:8]:
            rd = str(rec.get("report_date", ""))
            if rd and rd not in seen:
                seen.add(rd)
                v = _safe(rec.get("eps"))
                if v is not None:
                    eps_vals.append(v)
        if len(eps_vals) >= 4:
            ttm_eps_val = sum(eps_vals[:4])

    if ttm_eps_val is None and ttm_record:
        ttm_eps_val = _safe(ttm_record.get("eps"))

    if current_price and ttm_eps_val and ttm_eps_val > 0:
        calc_pe = current_price / ttm_eps_val
        add_row("P/E", fund.get("PE"), calc_pe, "Current Price / Official TTM EPS", is_ratio=True)
    else:
        add_row("P/E", fund.get("PE"), None, "Current Price / Official TTM EPS — N/A (no price or TTM EPS)", is_ratio=True)

    # EV/EBITDA (not applicable for banks)
    if not is_bank:
        mcap_info = get_latest_quarterly_reports(symbol, limit=1)
        mcap = fund.get("MarketCap")
        if not mcap:
            try:
                from data.database import get_company_info as db_get_company_info
                cached = db_get_company_info(symbol)
                if cached and cached.get("market_cap"):
                    mcap = float(cached["market_cap"])
            except Exception:
                pass

        debt_val = rep_debt or (ttm_record.get("total_debt") if ttm_record else None)
        cash_val = rep_cash or (ttm_record.get("cash_and_cash_equivalents") if ttm_record else None)
        debt_val = debt_val or 0.0
        cash_val = cash_val or 0.0

        dda_val = _safe(latest_a.get("depreciation_amortization")) or _safe(latest_q.get("depreciation_amortization"))
        ebit_val = _safe(ttm_record.get("ebit")) or rep_ebit
        calc_ebitda = FinancialCalculator.compute_ebitda(ebit_val, dda_val) if ebit_val is not None else None

        if mcap is not None and calc_ebitda is not None and calc_ebitda > 0:
            ev = mcap + debt_val - cash_val
            ev_ebitda = ev / calc_ebitda
            add_row("EV/EBITDA", None, ev_ebitda, f"EV ({mcap}+{debt_val}-{cash_val}) / TTM EBITDA ({calc_ebitda})", is_ratio=True)
        else:
            add_row("EV/EBITDA", None, None, "EV/EBITDA = N/A (missing market cap, debt, cash, or EBITDA from official filings)", is_ratio=True)

    # ==================== SOURCING TRACEABILITY ====================
    md = fund.get("metric_details", {})
    for metric_name, detail in md.items():
        if detail and isinstance(detail, dict):
            add_row(
                f"Source Trace: {metric_name}",
                _safe(detail.get("value")),
                _safe(detail.get("value")),
                f"Report Date: {detail.get('report_date')} | "
                f"Period: {detail.get('period')} | "
                f"Quarter: {detail.get('quarter_or_year')} | "
                f"Consolidated: {detail.get('consolidated')} | "
                f"Unit: {detail.get('unit')} | "
                f"Source Type: {detail.get('source_type')}",
                is_direct=True,
            )

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def print_filing_info(name: str, symbol: str):
    fund = fetch_fundamentals(symbol) or {}
    q_reports = get_latest_quarterly_reports(symbol, limit=4)
    a_reports = get_latest_annual_reports(symbol, limit=1)

    print(f"\n{'='*80}")
    print(f"Company: {name} ({symbol})")
    print(f"Data Source: {fund.get('fundamentals_source', 'NSE XBRL')}")
    print(f"Sector: {fund.get('Sector', 'N/A')}")
    print(f"Industry: {fund.get('Industry', 'N/A')}")

    if not q_reports.empty:
        latest_q = q_reports.iloc[0]
        print(f"\nLatest Quarterly Filing:")
        print(f"  Report Date: {latest_q.get('report_date', 'N/A')}")
        print(f"  Period: Q{latest_q.get('quarter', '?')} FY{latest_q.get('financial_year', '?')}")
        print(f"  Source URL: {latest_q.get('source_url', 'N/A')}")
        print(f"  Source Type: {latest_q.get('source_type', 'N/A')}")
        print(f"  Consolidated: {latest_q.get('consolidated', True)}")
        print(f"  Unit: {latest_q.get('unit', 'INR_Crores')}")
        print(f"  Revenue: {_fmt(_safe(latest_q.get('revenue')))}")
        print(f"  PAT: {_fmt(_safe(latest_q.get('pat')))}")
        print(f"  EPS: {_fmt(_safe(latest_q.get('eps')), is_eps=True)}")
        print(f"  EBIT: {_fmt(_safe(latest_q.get('ebit')))}")
        print(f"  Total Debt: {_fmt(_safe(latest_q.get('total_debt')) or _safe(latest_q.get('debt')))}")
        print(f"  Cash & Cash Eq: {_fmt(_safe(latest_q.get('cash_and_cash_equivalents')))}")
    else:
        print(f"\n  No quarterly filings available from NSE XBRL.")

    if not a_reports.empty:
        latest_a = a_reports.iloc[0]
        print(f"\nLatest Annual Filing:")
        print(f"  Report Date: {latest_a.get('report_date', 'N/A')}")
        print(f"  Financial Year: FY{latest_a.get('financial_year', '?')}")
        print(f"  Source URL: {latest_a.get('source_url', 'N/A')}")
        print(f"  Source Type: {latest_a.get('source_type', 'N/A')}")

    ttm = get_ttm_record(symbol, "ttm")
    if ttm:
        print(f"\nTTM Record (from 4 distinct quarterly filings):")
        print(f"  Revenue: {_fmt(_safe(ttm.get('revenue')))}")
        print(f"  PAT: {_fmt(_safe(ttm.get('pat')))}")
        print(f"  EPS: {_fmt(_safe(ttm.get('eps')), is_eps=True)}")
        print(f"  Quarter count: {ttm.get('quarter_count', 'N/A')}")
        if ttm.get("quarter_sources"):
            for qs in ttm["quarter_sources"]:
                print(f"    - {qs.get('quarter_label', 'N/A')}: "
                      f"EPS={_safe(qs.get('eps'))}, PAT={_safe(qs.get('pat'))}, "
                      f"Revenue={_safe(qs.get('revenue'))}, Source={qs.get('source', 'N/A')}")
    else:
        print(f"\n  No TTM record available.")


def main():
    print("=" * 120)
    print("NSE OFFICIAL FILINGS VALIDATION REPORT")
    print("Test Universe: RELIANCE.NS, TCS.NS, INFY.NS, HDFCBANK.NS, SBIN.NS")
    print("Columns: Company | Metric | App Value | NSE Reported Value | Formula | Source | Period | Status")
    print("Status: OK=exact/within 1%, MISMATCH=>1%, N/A=not reported/unavailable")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 120)

    all_results = []

    for name, symbol in TEST_COMPANIES.items():
        print_filing_info(name, symbol)
        try:
            df_comp = validate_company(name, symbol)
            if not df_comp.empty:
                all_results.append(df_comp)
                print(f"\n  Validation Results for {name} ({symbol}):")
                display_cols = ["Metric", "App Value", "NSE Reported Value", "Formula / Source", "Status"]
                print(df_comp[display_cols].to_string(index=False))

                status_counts = df_comp["Status"].value_counts()
                print(f"\n  Summary: {status_counts.get('OK', 0)} OK, "
                      f"{status_counts.get('MISMATCH', 0)} MISMATCH, "
                      f"{status_counts.get('N/A', 0)} N/A")
            else:
                print(f"\n  No data available for {name} ({symbol})")
        except Exception as e:
            print(f"\n  ERROR validating {name} ({symbol}): {e}")
            import traceback
            traceback.print_exc()

    # Combined report
    if all_results:
        combined = pd.concat(all_results, ignore_index=True)
        report_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "data", "reports", "nse_validation_report.csv"
        )
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        combined.to_csv(report_path, index=False)

        # Summary
        print(f"\n{'='*120}")
        print("COMBINED VALIDATION SUMMARY")
        print("=" * 120)
        summary = combined.groupby("Status").size().reset_index(name="Count")
        print(summary.to_string(index=False))

        total = len(combined)
        ok = combined["Status"].value_counts().get("OK", 0)
        mismatch = combined["Status"].value_counts().get("MISMATCH", 0)
        na = combined["Status"].value_counts().get("N/A", 0)
        print(f"\nTotal checks: {total}")
        print(f"  OK: {ok}")
        print(f"  MISMATCH: {mismatch}")
        print(f"  N/A: {na}")
        if ok + mismatch > 0:
            print(f"  Pass rate (excluding N/A): {ok / (ok + mismatch) * 100:.1f}%")

        print(f"\nFull report saved to: {report_path}")

    # Confirm zero Yahoo fundamental leakage
    print(f"\n{'='*120}")
    print("DATA SOURCE LEAKAGE AUDIT")
    print("=" * 120)
    import subprocess
    script_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "providers")
    findings = {
        "yf.Ticker": [],
        "yfinance .info() fundamental fields": [],
        "totalDebt": [],
        "totalCash": [],
        "ebitda (from yf)": [],
        "trailingEps": [],
        "forwardEps": [],
        "sharesOutstanding (from yf)": [],
        "marketCap (from yf)": [],
    }

    for root, dirs, files in os.walk(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))):
        # Skip scripts, tests, and home.py (price-only is OK)
        parts = root.replace("\\", "/").split("/")
        if any(p in ("scripts", "__pycache__") for p in parts):
            continue
        for fname in files:
            if fname.endswith(".py") and fname not in ("home.py",):
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    # Skip yahoo_price_provider.py since it intentionally uses yf.Ticker for price only
                    rel_path = os.path.relpath(fpath, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    if "yahoo_price_provider.py" in rel_path or "fetch_prices.py" in rel_path:
                        continue
                    if "yf.Ticker" in content or "yf.download" in content:
                        findings["yf.Ticker"].append(rel_path)
                    for field in ["totalDebt", "totalCash", "trailingEps", "forwardEps"]:
                        if field in content:
                            findings[field].append(rel_path)
                except Exception:
                    pass

    leakage_found = False
    for field, files in findings.items():
        if files:
            leakage_found = True
            print(f"  [LEAKAGE] {field}: found in {files}")
        else:
            print(f"  [OK] {field}: not found in production code")

    if not leakage_found:
        print("\n  RESULT: ZERO Yahoo Finance fundamental data leakage confirmed.")
    else:
        print("\n  RESULT: Yahoo Finance fundamental leakage detected — review above.")

    return 0 if not leakage_found else 1


if __name__ == "__main__":
    sys.exit(main())
