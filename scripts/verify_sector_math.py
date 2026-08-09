#!/usr/bin/env python3
"""Sector Engine Empirical Verification Script.

Displays the underlying constituent companies for each sector, their exact reporting period,
and the step-by-step mathematical derivation of Median P/E, Median ROE, and Sector Breadth (% > 200 EMA).
"""

import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.sector_data import STOCK_SECTOR_MAP, compute_sector_aggregated_metrics
from data.fetch_fundamentals import fetch_fundamentals
from data.fetch_prices import fetch_prices
from data.database import get_latest_quarterly_reports


SECTORS_TO_VERIFY = ["IT & Technology", "Banking & Financials", "Oil, Gas & Energy"]


def verify_sector(sector_name: str):
    print("=" * 110)
    print(f"SECTOR VERIFICATION: {sector_name}")
    print("=" * 110)

    constituents = [sym for sym, sec in STOCK_SECTOR_MAP.items() if sec == sector_name]
    print(f"Underlying Sector Constituents ({len(constituents)} companies): {', '.join(constituents)}")

    rows = []
    for sym in constituents:
        q_reports = get_latest_quarterly_reports(sym, limit=1)
        period = q_reports["report_date"].iloc[0] if not q_reports.empty else "N/A"
        fund = fetch_fundamentals(sym) or {}

        prices = fetch_prices(sym, period="1y")
        close_p = prices["Close"].iloc[-1] if not prices.empty else None
        ema200 = prices["Close"].ewm(span=200, adjust=False).mean().iloc[-1] if not prices.empty and len(prices) >= 200 else None
        above_200 = (close_p > ema200) if (close_p and ema200) else None

        pe = fund.get("PE")
        roe = fund.get("ROE")

        rows.append({
            "Symbol": sym,
            "Reporting Period": period,
            "P/E Ratio": round(pe, 2) if pe else None,
            "ROE (%)": round(roe * 100.0 if (roe and abs(roe) < 1.0) else roe, 2) if roe else None,
            "Close Price": round(close_p, 2) if close_p else None,
            "200 EMA": round(ema200, 2) if ema200 else None,
            "> 200 EMA": "YES" if above_200 else "NO",
        })

    df = pd.DataFrame(rows)
    print("\n--- CONSTITUENT DATA MATRIX ---")
    print(df.to_string(index=False))

    periods = df["Reporting Period"].unique()
    is_aligned = (len(periods) == 1)
    print(f"\nPeriod Alignment Status: {'UNIFIED (' + str(periods[0]) + ')' if is_aligned else 'MISALIGNED ' + str(periods)}")

    valid_pe = df["P/E Ratio"].dropna().sort_values().tolist()
    valid_roe = df["ROE (%)"].dropna().sort_values().tolist()
    above_cnt = (df["> 200 EMA"] == "YES").sum()
    total_cnt = len(df)
    breadth_pct = (above_cnt / total_cnt) * 100.0 if total_cnt > 0 else 0.0

    med_pe = np.median(valid_pe) if valid_pe else None
    med_roe = np.median(valid_roe) if valid_roe else None

    print("\n--- DERIVATION & MATH PROOF ---")
    print(f"Sorted P/E Values: {valid_pe} -> Median P/E: {med_pe:.2f}")
    print(f"Sorted ROE Values: {valid_roe} -> Median ROE: {med_roe:.2f}%")
    print(f"Stocks > 200 EMA: {above_cnt} / {total_cnt} -> Sector Breadth: {breadth_pct:.1f}%")
    print("=" * 110 + "\n")


def main():
    for sec in SECTORS_TO_VERIFY:
        verify_sector(sec)


if __name__ == "__main__":
    main()
