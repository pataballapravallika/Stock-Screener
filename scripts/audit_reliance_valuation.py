#!/usr/bin/env python3
"""Audit Reliance Valuation Module Script.

Fetches exact raw inputs for RELIANCE.NS, verifies TTM EPS sum over last 4 quarters,
computes P/E, PEG, EV/EBITDA, Market Cap, and compares against market data sources.
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.fetch_fundamentals import fetch_fundamentals
from data.fetch_prices import fetch_prices
from data.database import get_latest_quarterly_reports, get_latest_annual_reports, get_ttm_record


def audit_reliance():
    symbol = "RELIANCE.NS"
    print("=" * 80)
    print("RELIANCE INDUSTRIES (RELIANCE.NS) VALUATION AUDIT")
    print(f"Audit Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 1. Price Data & Shares Outstanding
    t = yf.Ticker(symbol)
    fi = getattr(t, "fast_info", {})
    t_info = t.info or {}

    prices = fetch_prices(symbol, period="5d")
    current_price = prices["Close"].iloc[-1] if not prices.empty else fi.get("lastPrice") or t_info.get("currentPrice")
    shares_outstanding = fi.get("shares") or t_info.get("sharesOutstanding")
    
    calc_mcap_cr = (current_price * shares_outstanding) / 1e7 if (current_price and shares_outstanding) else None
    yf_mcap_cr = (fi.get("marketCap") or t_info.get("marketCap", 0)) / 1e7

    print("\n--- MARKET CAP INPUTS ---")
    print(f"Current Price        : INR {current_price:.2f}")
    print(f"Shares Outstanding   : {shares_outstanding:,.0f}")
    print(f"Calculated Market Cap: INR {calc_mcap_cr:,.2f} Cr")
    print(f"YFinance Market Cap  : INR {yf_mcap_cr:,.2f} Cr")
    print(f"Calculation Date     : {datetime.now().strftime('%Y-%m-%d')}")
    print("Formula              : Market Cap = Current Price * Shares Outstanding / 10^7")

    # 2. Quarterly Filings & TTM EPS
    from data.calculations.financial_calculator import FinancialCalculator
    q_df = get_latest_quarterly_reports(symbol, limit=4)
    print("\n--- LAST 4 DISTINCT QUARTERLY REPORTS ---")
    ttm_calc = FinancialCalculator.compute_ttm(q_df.to_dict("records")) if not q_df.empty else None

    if ttm_calc and ttm_calc.get("quarter_sources"):
        print(f"{'Source Period Date':<20} | {'Quarter Label':<12} | {'EPS (INR)':<10} | {'PAT (INR Cr)':<14} | {'Revenue (INR Cr)':<16} | {'Source':<12}")
        print("-" * 100)
        for q in ttm_calc["quarter_sources"]:
            print(f"{q['report_date']:<20} | {q['quarter_label']:<12} | {q['eps']:<10.2f} | {q['pat']:<14,.2f} | {q['revenue']:<16,.2f} | {q['source']:<12}")

    ttm_revenue = ttm_calc.get("revenue") if ttm_calc else None
    ttm_pat = ttm_calc.get("pat") if ttm_calc else None
    ttm_eps_sum = ttm_calc.get("eps") if ttm_calc else None
    ttm_ebit = ttm_calc.get("ebit") if ttm_calc else None

    # YFinance Trailing EPS
    yf_trailing_eps = t_info.get("trailingEps")

    print("\n--- TTM AGGREGATES ---")
    print(f"TTM Revenue          : INR {ttm_revenue:,.2f} Cr" if ttm_revenue else "TTM Revenue: N/A")
    print(f"TTM PAT              : INR {ttm_pat:,.2f} Cr" if ttm_pat else "TTM PAT: N/A")
    print(f"TTM EBIT/EBITDA      : INR {ttm_ebit:,.2f} Cr" if ttm_ebit else "TTM EBIT: N/A")
    print(f"TTM EPS (4-Qtr Sum)  : INR {ttm_eps_sum:.2f}" if ttm_eps_sum else "TTM EPS: N/A")

    print("\n--- P/E RATIO INPUTS ---")
    print(f"Current Market Price : INR {current_price:.2f}")
    print(f"TTM EPS              : INR {ttm_eps_sum:.2f}" if ttm_eps_sum else "TTM EPS: N/A")
    print(f"YFinance Trailing EPS: INR {yf_trailing_eps:.2f}" if yf_trailing_eps else "YFinance Trailing EPS: N/A")
    calc_pe = (current_price / ttm_eps_sum) if (current_price and ttm_eps_sum and ttm_eps_sum > 0) else None
    yf_pe = t_info.get("trailingPE")
    print(f"Calculated P/E       : {calc_pe:.2f}" if calc_pe else "Calculated P/E: N/A")
    print(f"YFinance Trailing P/E: {yf_pe:.2f}" if yf_pe else "YFinance P/E: N/A")
    print(f"Calculation Date     : {datetime.now().strftime('%Y-%m-%d')}")
    print("Formula              : P/E = Current Market Price / TTM EPS")

    # 3. PEG Ratio Inputs
    fund = fetch_fundamentals(symbol) or {}
    eps_growth_pct = fund.get("EPS_YoY") or fund.get("Sales_YoY") or fund.get("EarningsGrowth") or 10.0
    calc_peg = (calc_pe / eps_growth_pct) if (calc_pe and eps_growth_pct and eps_growth_pct > 0) else None
    yf_peg = t_info.get("pegRatio")

    print("\n--- PEG RATIO INPUTS ---")
    print(f"P/E Ratio            : {calc_pe:.2f}" if calc_pe else f"P/E Ratio: {yf_pe:.2f}" if yf_pe else "N/A")
    print(f"EPS Growth %         : {eps_growth_pct:.2f}%")
    print("Growth Period        : Trailing 12 Months (YoY)")
    print(f"Calculated PEG       : {calc_peg:.2f}" if calc_peg else "Calculated PEG: N/A")
    print(f"YFinance PEG         : {yf_peg:.2f}" if yf_peg else "YFinance PEG: N/A")
    print("Formula              : PEG = P/E / EPS Growth %")

    # 4. EV/EBITDA Inputs
    total_debt_cr = (t_info.get("totalDebt", 0)) / 1e7
    total_cash_cr = (t_info.get("totalCash", 0)) / 1e7
    mcap_for_ev = calc_mcap_cr or yf_mcap_cr
    calc_ev_cr = mcap_for_ev + total_debt_cr - total_cash_cr if mcap_for_ev else None

    ebitda_cr = ttm_ebit or ((t_info.get("ebitda", 0)) / 1e7)
    calc_ev_ebitda = (calc_ev_cr / ebitda_cr) if (calc_ev_cr and ebitda_cr and ebitda_cr > 0) else None
    yf_ev_ebitda = t_info.get("enterpriseToEbitda")

    print("\n--- EV/EBITDA INPUTS ---")
    print(f"Market Cap           : INR {mcap_for_ev:,.2f} Cr")
    print(f"Total Debt           : INR {total_debt_cr:,.2f} Cr")
    print(f"Cash & Equivalents   : INR {total_cash_cr:,.2f} Cr")
    print(f"Enterprise Value (EV): INR {calc_ev_cr:,.2f} Cr" if calc_ev_cr else "EV: N/A")
    print(f"TTM EBITDA           : INR {ebitda_cr:,.2f} Cr" if ebitda_cr else "EBITDA: N/A")
    print(f"Calculated EV/EBITDA : {calc_ev_ebitda:.2f}x" if calc_ev_ebitda else "Calculated EV/EBITDA: N/A")
    print(f"YFinance EV/EBITDA   : {yf_ev_ebitda:.2f}x" if yf_ev_ebitda else "YFinance EV/EBITDA: N/A")
    print("Formula              : Enterprise Value = Market Cap + Total Debt - Cash")
    print("                       EV/EBITDA = Enterprise Value / TTM EBITDA")

    print("\n" + "=" * 80)
    print("AUDIT COMPLETED SUCCESSFULLY")
    print("=" * 80)


if __name__ == "__main__":
    audit_reliance()
