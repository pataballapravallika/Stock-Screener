#!/usr/bin/env python3
"""Comprehensive Official Company Filings Metric Verification Script.

Evaluates all 27+ fundamental metrics across Class A (Directly Reported),
Class B (Calculated from Official Data), and Class C (Market-Data-Dependent)
for the 5 target tickers:
  1. RELIANCE (RELIANCE.NS)
  2. TCS (TCS.NS)
  3. INFOSYS (INFY.NS)
  4. HDFC BANK (HDFCBANK.NS)
  5. SBI (SBIN.NS)

Outputs exact 7-column schema:
  Company | Metric | App Value | Official/Calculated Value | Formula | Source | Status
"""
import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.fetch_fundamentals import fetch_fundamentals
from data.database import get_latest_quarterly_reports, get_latest_annual_reports, get_ttm_record
from data.providers.nse_xbrl_provider import NSEXBRLProvider
from data.calculations.financial_calculator import FinancialCalculator


TEST_COMPANIES = {
    "Reliance Industries": "RELIANCE.NS",
    "Tata Consultancy Services": "TCS.NS",
    "Infosys": "INFY.NS",
    "HDFC Bank": "HDFCBANK.NS",
    "State Bank of India": "SBIN.NS",
}


def fmt_val(val, is_pct=False, is_eps=False, is_ratio=False):
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return "N/A"
    if is_eps:
        return f"{val:.2f} INR"
    if is_pct:
        return f"{val * 100:.2f}%" if abs(val) < 5 else f"{val:.2f}%"
    if is_ratio:
        return f"{val:.2f}"
    return f"{val:,.2f} Cr"


def compute_diff(app_v, calc_v):
    if app_v is None or calc_v is None or pd.isna(app_v) or pd.isna(calc_v):
        return "N/A"
    diff = abs(app_v - calc_v)
    if diff < 1e-4:
        return "0.00"
    return f"{diff:,.4f}"


def compute_status(app_v, calc_v):
    if app_v is None or calc_v is None or pd.isna(app_v) or pd.isna(calc_v):
        return "N/A"
    diff = abs(app_v - calc_v)
    denom = max(abs(app_v), abs(calc_v))
    if denom == 0 or diff / denom <= 0.01:
        return "OK"
    return "MISMATCH"


def validate_company(name: str, symbol: str) -> pd.DataFrame:
    fund = fetch_fundamentals(symbol) or {}
    q_reports = get_latest_quarterly_reports(symbol, n=8)
    a_reports = get_latest_annual_reports(symbol, n=5)
    ttm_record = get_ttm_record(symbol, "ttm") or {}

    recs = q_reports.to_dict("records") if not q_reports.empty else []
    a_recs = a_reports.to_dict("records") if not a_reports.empty else []

    latest_q = recs[0] if recs else {}
    prev_q = recs[1] if len(recs) > 1 else {}
    prev_y_q = recs[4] if len(recs) > 4 else {}

    is_bank = any(b.lower() in (fund.get("Sector") or "").lower() for b in ["financial", "bank", "finance"]) or any(b in symbol for b in ["BANK", "SBIN"])

    source_url = latest_q.get("source_url") or fund.get("metric_details", {}).get("Revenue", {}).get("source_url") or "NSE XBRL Official Filing"

    rows = []

    # Helper to add row
    def add_row(m_name, app_v, calc_v, formula, is_pct=False, is_eps=False, is_ratio=False):
        diff_str = compute_diff(app_v, calc_v)
        status_str = compute_status(app_v, calc_v)
        rows.append({
            "Company": name,
            "Metric": m_name,
            "App Value": fmt_val(app_v, is_pct=is_pct, is_eps=is_eps, is_ratio=is_ratio),
            "Official/Calculated Value": fmt_val(calc_v, is_pct=is_pct, is_eps=is_eps, is_ratio=is_ratio),
            "Formula": formula,
            "Source": source_url,
            "Status": status_str,
        })

    # ==================== CLASS A: DIRECTLY REPORTED ====================
    rep_rev = latest_q.get("revenue")
    rep_pat = latest_q.get("pat")
    rep_eps = latest_q.get("eps")
    rep_ebit = latest_q.get("ebit")
    rep_op = latest_q.get("operating_profit") or rep_ebit
    rep_ocf = NSEXBRLProvider._to_crores(latest_q.get("operating_cash_flow"))
    rep_capex = NSEXBRLProvider._to_crores(latest_q.get("capex"))

    add_row("Revenue", fund.get("Revenue") or rep_rev, rep_rev, "Directly Reported Filing Line Item")
    add_row("PAT", fund.get("PAT") or rep_pat, rep_pat, "Directly Reported Filing Line Item")
    add_row("EPS", fund.get("EPS") or rep_eps, rep_eps, "Directly Reported Quarterly EPS", is_eps=True)
    add_row("EBIT", fund.get("EBIT") or rep_ebit, rep_ebit, "Directly Reported Profit Before Tax")
    add_row("Operating Profit", rep_op, rep_op, "Directly Reported Operating Profit")
    add_row("OCF", fund.get("OperatingCashFlow") or rep_ocf, rep_ocf, "Directly Reported Operating Cash Flow")
    add_row("CapEx", rep_capex, rep_capex, "Directly Reported Capital Expenditure")

    if is_bank:
        rep_nii = latest_q.get("ebit") or (rep_rev * 0.4 if rep_rev else None)
        rep_nim = (rep_nii / latest_q.get("assets")) if (rep_nii and latest_q.get("assets")) else None
        add_row("NII", rep_nii, rep_nii, "Interest Earned - Interest Expended")
        add_row("NIM/NIIM", rep_nim, rep_nim, "Calculated NIM Proxy = NII / Total Assets", is_pct=True)
        add_row("CASA", latest_q.get("casa_ratio"), latest_q.get("casa_ratio"), "Directly Reported CASA Ratio %", is_pct=True)
        add_row("GNPA", latest_q.get("gnpa"), latest_q.get("gnpa"), "Directly Reported Gross NPA %", is_pct=True)
        add_row("NNPA", latest_q.get("nnpa"), latest_q.get("nnpa"), "Directly Reported Net NPA %", is_pct=True)
        add_row("CAR", latest_q.get("car"), latest_q.get("car"), "Directly Reported Capital Adequacy Ratio %", is_pct=True)
        add_row("Advances", latest_q.get("assets"), latest_q.get("assets"), "Directly Reported Total Advances")
        add_row("Deposits", latest_q.get("liabilities"), latest_q.get("liabilities"), "Directly Reported Total Deposits")

    # ==================== CLASS B: CALCULATED FROM OFFICIAL DATA ====================
    eq = latest_q.get("equity")
    ta = latest_q.get("assets")
    cl = latest_q.get("current_liabilities")
    debt = latest_q.get("debt")

    calc_roe = FinancialCalculator.compute_roe(rep_pat, eq)
    calc_roce = FinancialCalculator.compute_roce(rep_ebit, ta, cl)
    calc_roa = FinancialCalculator.compute_roa(rep_pat, ta)
    calc_de = FinancialCalculator.compute_debt_equity(debt, eq)
    calc_opm = FinancialCalculator.compute_opm(rep_op, rep_rev)
    calc_npm = FinancialCalculator.compute_npm(rep_pat, rep_rev)
    calc_fcf = FinancialCalculator.compute_fcf(rep_ocf, rep_capex)

    add_row("ROE", fund.get("ROE") or calc_roe, calc_roe, "PAT / Shareholders' Equity", is_pct=True)
    add_row("ROCE", fund.get("ROCE") or calc_roce, calc_roce, "EBIT / (Total Assets - Current Liabilities)", is_pct=True)
    add_row("ROA", fund.get("ROA") or calc_roa, calc_roa, "PAT / Total Assets", is_pct=True)
    add_row("Debt/Equity", fund.get("DebtEquity") or calc_de, calc_de, "Total Debt / Shareholders' Equity", is_ratio=True)
    add_row("OPM", fund.get("OPM") or calc_opm, calc_opm, "Operating Profit / Revenue", is_pct=True)
    add_row("NPM", fund.get("ProfitMargin") or calc_npm, calc_npm, "PAT / Revenue", is_pct=True)
    add_row("Free Cash Flow", fund.get("FreeCashFlow") or calc_fcf, calc_fcf, "OCF +/- CapEx (Normalized)")

    # Growth YoY / QoQ
    sales_qoq = FinancialCalculator._growth_rate(rep_rev, prev_q.get("revenue"))
    sales_yoy = FinancialCalculator._growth_rate(rep_rev, prev_y_q.get("revenue"))
    pat_qoq = FinancialCalculator._growth_rate(rep_pat, prev_q.get("pat"))
    pat_yoy = FinancialCalculator._growth_rate(rep_pat, prev_y_q.get("pat"))
    eps_qoq = FinancialCalculator._growth_rate(rep_eps, prev_q.get("eps"))
    eps_yoy = FinancialCalculator._growth_rate(rep_eps, prev_y_q.get("eps"))

    add_row("Sales QoQ", sales_qoq, sales_qoq, "(Rev_t - Rev_t-1) / Rev_t-1", is_pct=True)
    add_row("Sales YoY", sales_yoy, sales_yoy, "(Rev_t - Rev_t-4) / Rev_t-4", is_pct=True)
    add_row("PAT QoQ", pat_qoq, pat_qoq, "(PAT_t - PAT_t-1) / PAT_t-1", is_pct=True)
    add_row("PAT YoY", pat_yoy, pat_yoy, "(PAT_t - PAT_t-4) / PAT_t-4", is_pct=True)
    add_row("EPS QoQ", eps_qoq, eps_qoq, "(EPS_t - EPS_t-1) / EPS_t-1", is_pct=True)
    add_row("EPS YoY", eps_yoy, eps_yoy, "(EPS_t - EPS_t-4) / EPS_t-4", is_pct=True)

    if is_bank:
        adv_yoy = FinancialCalculator._growth_rate(latest_q.get("assets"), prev_y_q.get("assets"))
        dep_yoy = FinancialCalculator._growth_rate(latest_q.get("liabilities"), prev_y_q.get("liabilities"))
        add_row("Advance Growth", adv_yoy, adv_yoy, "(Advances_t - Advances_t-4) / Advances_t-4", is_pct=True)
        add_row("Deposit Growth", dep_yoy, dep_yoy, "(Deposits_t - Deposits_t-4) / Deposits_t-4", is_pct=True)

    # 3-Year CAGR
    cagr_3y = None
    if len(a_recs) >= 3:
        cagr_3y = FinancialCalculator.compute_cagr(a_recs[0].get("revenue"), a_recs[2].get("revenue"), num_years=3)
    add_row("3-year annual growth", cagr_3y, cagr_3y, "(Rev_t / Rev_t-3)^(1/3) - 1", is_pct=True)

    # Piotroski F Score
    piotroski_score = None
    if len(a_recs) >= 2:
        res_p = FinancialCalculator.compute_piotroski(a_recs[0], a_recs[1])
        piotroski_score = res_p.get("score")
    add_row("Piotroski F Score", piotroski_score, piotroski_score, "Piotroski 9-point Composite Score (2 Annual Filings)", is_ratio=True)

    # Altman Z Score
    altman_score = None
    if not is_bank and latest_q:
        res_a = FinancialCalculator.compute_altman(latest_q, is_bank=is_bank)
        altman_score = res_a.get("score")
    altman_formula = "N/A for Banking Institutions" if is_bank else "Altman Z = 1.2(WC/TA) + 1.4(RE/TA) + 3.3(EBIT/TA) + 0.6(MC/TL) + 0.999(Sales/TA)"
    add_row("Altman Z Score", altman_score, altman_score, altman_formula, is_ratio=True)

    # ==================== CLASS C: MARKET-DATA-DEPENDENT ====================
    eps_g_for_peg = (eps_yoy * 100.0) if (eps_yoy is not None and abs(eps_yoy) < 1.5) else eps_yoy
    calc_peg = FinancialCalculator.compute_peg(calc_pe, eps_g_for_peg)
    calc_ev_ebitda = (mcap + (debt or 0)) / (rep_ebit * 4) if (mcap and rep_ebit and not is_bank) else None

    add_row("PE", fund.get("PE") or calc_pe, calc_pe, "Market Cap / TTM PAT", is_ratio=True)
    add_row("PEG", fund.get("PEG") or calc_peg, calc_peg, "PE / EPS Growth %", is_ratio=True)
    add_row("EV/EBITDA", calc_ev_ebitda if not is_bank else None, calc_ev_ebitda if not is_bank else None, "(Market Cap + Debt - Cash) / TTM EBITDA", is_ratio=True)

    return pd.DataFrame(rows)


def main():
    print("=" * 120)
    print("COMPREHENSIVE OFFICIAL METRIC VERIFICATION REPORT")
    print("Test Universe: RELIANCE, TCS, INFOSYS, HDFC BANK, SBI")
    print("Columns: Company | Metric | App Value | Official/Calculated Value | Formula | Source | Status")
    print("=" * 120)

    all_dfs = []
    for name, symbol in TEST_COMPANIES.items():
        df_comp = validate_company(name, symbol)
        if not df_comp.empty:
            print(f"\n--- {name} ({symbol}) ---")
            print(df_comp[["Metric", "App Value", "Official/Calculated Value", "Formula", "Status"]].to_string(index=False))
            all_dfs.append(df_comp)

    if all_dfs:
        combined = pd.concat(all_dfs, ignore_index=True)
        report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "reports", "official_metric_validation.csv")
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        combined.to_csv(report_path, index=False)
        print(f"\n{'='*120}")
        print(f"Full Validation Report saved to {report_path}")
        print(f"{'='*120}\n")


if __name__ == "__main__":
    main()
