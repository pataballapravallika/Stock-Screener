#!/usr/bin/env python3
"""Verification script for the new fundamental data layer.

Tests the modular provider architecture against:
  RELIANCE.NS, TCS.NS, INFY.NS, HDFCBANK.NS, SBIN.NS

Produces a structured report with:
  - data source
  - extracted values
  - calculated values
  - validation status
  - missing values
"""
import sys
import os
import json
import sqlite3
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.fetch_fundamentals import fetch_fundamentals
from data.database import (
    get_latest_quarterly_reports,
    get_latest_annual_reports,
    get_ttm_record,
    save_validation_report,
    get_validation_reports,
    init_db,
    DB,
)
from data.calculations.validation import ValidationEngine
from data.calculations.financial_calculator import FinancialCalculator
from fundamentals.ratios import safe_float


TEST_TICKERS = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "SBIN.NS"]


def get_db_records(ticker):
    q = get_latest_quarterly_reports(ticker, n=8)
    a = get_latest_annual_reports(ticker, n=5)
    ttm = get_ttm_record(ticker, "ttm")
    return q, a, ttm


def format_record(r):
    return {
        "report_date": r.get("report_date"),
        "period": r.get("period"),
        "financial_year": r.get("financial_year"),
        "quarter": r.get("quarter"),
        "revenue": safe_float(r.get("revenue")),
        "operating_profit": safe_float(r.get("operating_profit")),
        "ebit": safe_float(r.get("ebit")),
        "pat": safe_float(r.get("pat")),
        "eps": safe_float(r.get("eps")),
        "equity": safe_float(r.get("equity")),
        "assets": safe_float(r.get("assets")),
        "liabilities": safe_float(r.get("liabilities")),
        "current_liabilities": safe_float(r.get("current_liabilities")),
        "debt": safe_float(r.get("debt")),
        "operating_cash_flow": safe_float(r.get("operating_cash_flow")),
        "capex": safe_float(r.get("capex")),
        "source": r.get("source"),
    }


def verify_ticker(ticker):
    print(f"\n{'='*80}")
    print(f"Verifying: {ticker}")
    print(f"{'='*80}")

    fund = fetch_fundamentals(ticker)
    if not fund:
        print(f"  ERROR: Could not fetch fundamentals for {ticker}")
        return None

    source = fund.get("fundamentals_source", "unknown")
    print(f"  Data source: {source}")

    q_df = fund.get("quarterly_financials")
    a_df = fund.get("annual_financials")
    q_balance = fund.get("quarterly_balance_sheet")
    a_balance = fund.get("balance_sheet")
    cf = fund.get("cashflow")

    print(f"  Quarterly financials: {'Available (' + str(q_df.shape[1]) + ' periods)' if q_df is not None and not q_df.empty else 'Missing'}")
    print(f"  Annual financials: {'Available (' + str(a_df.shape[1]) + ' periods)' if a_df is not None and not a_df.empty else 'Missing'}")
    print(f"  Quarterly balance sheet: {'Available' if q_balance is not None and not q_balance.empty else 'Missing'}")
    print(f"  Annual balance sheet: {'Available' if a_balance is not None and not a_balance.empty else 'Missing'}")
    print(f"  Cashflow: {'Available' if cf is not None and not cf.empty else 'Missing'}")

    q_reports, a_reports, ttm_record = get_db_records(ticker)

    records = {
        "quarterly": [format_record(r) for _, r in q_reports.iterrows()] if not q_reports.empty else [],
        "annual": [format_record(r) for _, r in a_reports.iterrows()] if not a_reports.empty else [],
        "ttm": format_record(ttm_record) if ttm_record else None,
    }

    if records["quarterly"]:
        latest_q = records["quarterly"][0]
        print(f"\n  Latest Quarterly ({latest_q.get('report_date')}):")
        print(f"    Revenue:     {latest_q.get('revenue')}")
        print(f"    Operating Profit: {latest_q.get('operating_profit')}")
        print(f"    EBIT:        {latest_q.get('ebit')}")
        print(f"    PAT:         {latest_q.get('pat')}")
        print(f"    EPS:         {latest_q.get('eps')}")
        print(f"    Equity:      {latest_q.get('equity')}")
        print(f"    Assets:      {latest_q.get('assets')}")
        print(f"    Liabilities: {latest_q.get('liabilities')}")
        print(f"    Current Liab:{latest_q.get('current_liabilities')}")
        print(f"    Debt:        {latest_q.get('debt')}")
        print(f"    OCF:         {latest_q.get('operating_cash_flow')}")
        print(f"    CapEx:       {latest_q.get('capex')}")

    if records["annual"]:
        latest_a = records["annual"][0]
        print(f"\n  Latest Annual (FY{latest_a.get('financial_year')}):")
        print(f"    Revenue:     {latest_a.get('revenue')}")
        print(f"    PAT:         {latest_a.get('pat')}")
        print(f"    EPS:         {latest_a.get('eps')}")

    if records["ttm"]:
        ttm = records["ttm"]
        print(f"\n  TTM:")
        print(f"    Revenue:     {ttm.get('revenue')}")
        print(f"    PAT:         {ttm.get('pat')}")
        print(f"    FCF:         {ttm.get('operating_cash_flow')} + {ttm.get('capex')} = {FinancialCalculator.compute_fcf(ttm.get('operating_cash_flow'), ttm.get('capex'))}")

    ratios = {}
    target = None
    if records["quarterly"]:
        target = records["quarterly"][0]
    elif records["annual"]:
        target = records["annual"][0]
    elif records["ttm"]:
        target = records["ttm"]

    if target:
        ratios = FinancialCalculator.compute_all_ratios(target)
        print(f"\n  Ratios:")
        print(f"    ROE:         {ratios.get('roe')}")
        print(f"    ROA:         {ratios.get('roa')}")
        print(f"    ROCE:        {ratios.get('roce')}")
        print(f"    Debt/Equity: {ratios.get('debt_equity')}")
        print(f"    OPM:         {ratios.get('opm')}")
        print(f"    NPM:         {ratios.get('npm')}")
        print(f"    FCF:         {ratios.get('fcf')}")

    q_growth = FinancialCalculator.compute_quarterly_growth(records["quarterly"])
    a_growth = FinancialCalculator.compute_annual_growth(records["annual"])

    print(f"\n  Quarterly Growth:")
    for k, v in q_growth.items():
        print(f"    {k}: {v}")

    print(f"\n  Annual Growth:")
    for k, v in a_growth.items():
        print(f"    {k}: {v}")

    piotroski = {}
    if len(records["annual"]) >= 2:
        piotroski = FinancialCalculator.compute_piotroski(records["annual"][0], records["annual"][1])
        print(f"\n  Piotroski F-Score: {piotroski.get('score')}/9")

    altman = {}
    if target:
        altman = FinancialCalculator.compute_altman(target)
        print(f"  Altman Z-Score: {altman.get('value')} ({altman.get('status')})")

    missing = []
    if not records["quarterly"] and not records["annual"]:
        missing.append("quarterly and annual reports")
    else:
        if not records["quarterly"]:
            missing.append("quarterly reports")
        if not records["annual"]:
            missing.append("annual reports")
        if not records["ttm"]:
            missing.append("TTM record")

    if target:
        for key in ["revenue", "operating_profit", "ebit", "pat", "eps", "equity", "assets", "liabilities", "current_liabilities", "debt", "operating_cash_flow", "capex"]:
            if target.get(key) is None:
                missing.append(key)

    if missing:
        print(f"\n  Missing values: {', '.join(missing)}")
    else:
        print(f"\n  Missing values: None")

    engine = ValidationEngine(threshold=0.05)
    validation_report = engine.validate_company(ticker, records)
    engine.print_summary(validation_report)

    report_path = engine.save_report(validation_report)
    print(f"  Validation report saved: {report_path}")

    with sqlite3.connect(DB) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO validation_reports (ticker, report_json) VALUES (?, ?)",
            (ticker, json.dumps(validation_report, default=str)),
        )
        conn.commit()

    return {
        "ticker": ticker,
        "source": source,
        "quarterly_count": len(records["quarterly"]),
        "annual_count": len(records["annual"]),
        "has_ttm": bool(records["ttm"]),
        "ratios": {k: v for k, v in ratios.items()},
        "q_growth": q_growth,
        "a_growth": a_growth,
        "piotroski": piotroski,
        "altman": altman,
        "missing": missing,
        "validation": validation_report,
    }


def main():
    print("Fundamental Data Layer Verification")
    print("=" * 80)
    print(f"Verification time: {datetime.utcnow().isoformat()}")

    init_db()

    results = []
    for ticker in TEST_TICKERS:
        try:
            r = verify_ticker(ticker)
            if r:
                results.append(r)
        except Exception as e:
            print(f"  ERROR verifying {ticker}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*80}")
    print("OVERALL SUMMARY")
    print(f"{'='*80}")
    for r in results:
        s = r["validation"]["summary"]
        status = "PASS" if s["mismatches"] == 0 else "REVIEW"
        print(f"  {r['ticker']:15s} | source={r['source']:20s} | Q={r['quarterly_count']} | A={r['annual_count']} | TTM={'Yes' if r['has_ttm'] else 'No'} | mismatches={s['mismatches']} | {status}")

    output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", "verification_report.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nFull report saved to: {output_path}")


if __name__ == "__main__":
    main()
