#!/usr/bin/env python3
"""Test script for official reports provider.

Tests with:
- RELIANCE.NS
- TCS.NS
- INFY.NS
- HDFCBANK.NS
- SBIN.NS

Verifies Quarterly EPS against the latest official quarterly report.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from data.fetch_fundamentals import fetch_fundamentals
from data.database import (
    get_latest_quarterly_reports, get_latest_annual_reports,
    get_ttm_record, init_db
)
from data.providers.official_reports import OfficialReportsProvider


TEST_COMPANIES = {
    "Reliance Industries": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "Infosys": "INFY.NS",
    "HDFC Bank": "HDFCBANK.NS",
    "SBI": "SBIN.NS",
}


def test_provider():
    print("Testing Official Reports Provider")
    print("=" * 80)

    provider = OfficialReportsProvider()
    init_db()

    results = []
    for name, symbol in TEST_COMPANIES.items():
        print(f"\n--- {name} ({symbol}) ---")

        try:
            info = provider.get_info(symbol)
            print(f"  Company: {info.get('company_name', 'N/A')}")
            print(f"  Sector: {info.get('sector', 'N/A')}")
            print(f"  Industry: {info.get('industry', 'N/A')}")
            print(f"  Market Cap: {info.get('market_cap', 'N/A')}")
            print(f"  Shares Outstanding: {info.get('sharesOutstanding', 'N/A')}")
        except Exception as e:
            print(f"  ERROR fetching info: {e}")
            continue

        try:
            q_fin = provider.get_quarterly_financials(symbol)
            if q_fin is not None and not q_fin.empty:
                print(f"  Quarterly Financials: {len(q_fin.columns)} periods")
                print(f"  Columns: {list(q_fin.columns)}")
                print(f"  Index labels: {list(q_fin.index)}")
            else:
                print("  Quarterly Financials: N/A")
        except Exception as e:
            print(f"  ERROR fetching quarterly financials: {e}")

        try:
            annual_income = provider.get_annual_financials(symbol)
            if annual_income is not None and not annual_income.empty:
                print(f"  Annual Financials: {len(annual_income.columns)} years")
            else:
                print("  Annual Financials: N/A")
        except Exception as e:
            print(f"  ERROR fetching annual financials: {e}")

        try:
            balance_sheet = provider.get_balance_sheet(symbol)
            if balance_sheet is not None and not balance_sheet.empty:
                print(f"  Balance Sheet: available")
            else:
                print("  Balance Sheet: N/A")
        except Exception as e:
            print(f"  ERROR fetching balance sheet: {e}")

        try:
            cashflow = provider.get_cashflow(symbol)
            if cashflow is not None and not cashflow.empty:
                print(f"  Cash Flow: available")
            else:
                print("  Cash Flow: N/A")
        except Exception as e:
            print(f"  ERROR fetching cashflow: {e}")

        try:
            fund = provider.build_fundamentals_dict(symbol)
            print(f"\n  Fundamentals Summary:")
            print(f"    ROE: {fund.get('ROE')}")
            print(f"    ROCE: {fund.get('ROCE')}")
            print(f"    ROA: {fund.get('ROA')}")
            print(f"    Debt/Equity: {fund.get('DebtEquity')}")
            print(f"    EPS Growth: {fund.get('EarningsGrowth')}")
            print(f"    Revenue Growth: {fund.get('RevenueGrowth')}")
            print(f"    EBIT: {fund.get('EBIT')}")
            print(f"    Piotroski F-Score: {fund.get('piotroski_f_score', {}).get('score') if isinstance(fund.get('piotroski_f_score'), dict) else fund.get('piotroski_f_score')}")
            print(f"    Altman Z-Score: {fund.get('altman_z_score', {}).get('value') if isinstance(fund.get('altman_z_score'), dict) else fund.get('altman_z_score')}")

            q_reports = get_latest_quarterly_reports(symbol, n=4)
            if not q_reports.empty:
                latest_q = q_reports.iloc[0]
                print(f"\n  Latest Quarterly Report:")
                print(f"    Report Date: {latest_q.get('report_date')}")
                print(f"    Quarter: {latest_q.get('quarter')}")
                print(f"    Financial Year: {latest_q.get('financial_year')}")
                print(f"    Revenue: {latest_q.get('revenue')}")
                print(f"    Operating Profit: {latest_q.get('operating_profit')}")
                print(f"    EBIT: {latest_q.get('ebit')}")
                print(f"    PAT: {latest_q.get('pat')}")
                print(f"    EPS: {latest_q.get('eps')}")
                print(f"    Equity: {latest_q.get('equity')}")
                print(f"    Assets: {latest_q.get('assets')}")
                print(f"    Liabilities: {latest_q.get('liabilities')}")
                print(f"    Current Liabilities: {latest_q.get('current_liabilities')}")
                print(f"    Debt: {latest_q.get('debt')}")
                print(f"    Operating Cash Flow: {latest_q.get('operating_cash_flow')}")
                print(f"    CapEx: {latest_q.get('capex')}")

            ttm = get_ttm_record(symbol, "ttm")
            if ttm:
                print(f"\n  TTM Record:")
                print(f"    Revenue: {ttm.get('revenue')}")
                print(f"    PAT: {ttm.get('pat')}")
                print(f"    EPS: {ttm.get('eps')}")
                print(f"    ROE: {ttm.get('roe')}")
                print(f"    FCF: {ttm.get('fcf')}")

            results.append({
                "symbol": symbol,
                "company": name,
                "quarterly_eps": latest_q.get("eps") if not q_reports.empty else None,
                "annual_revenue": latest_q.get("revenue") if not q_reports.empty else None,
                "roe": fund.get("ROE"),
                "roce": fund.get("ROCE"),
                "roa": fund.get("ROA"),
                "debt_equity": fund.get("DebtEquity"),
                "eps_growth": fund.get("EarningsGrowth"),
                "revenue_growth": fund.get("RevenueGrowth"),
            })

        except Exception as e:
            print(f"  ERROR building fundamentals dict: {e}")

    if results:
        results_df = pd.DataFrame(results)
        results_df.to_csv("test_results.csv", index=False)
        print(f"\n\nResults saved to test_results.csv")
        print(results_df.to_string(index=False))


if __name__ == "__main__":
    test_provider()
