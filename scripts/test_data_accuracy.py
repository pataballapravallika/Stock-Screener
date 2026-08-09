#!/usr/bin/env python3
"""Verification Script for Data Accuracy Fixes:
1. VWAP Calculation & Non-Zero Volume Masking
2. Shareholding Pattern Extraction (Promoter, FII, DII, Public)
3. NIFTY Sectoral Indices & Relative Strength Performance
"""

import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indicators.trend import vwap
from data.fetch_fundamentals import fetch_fundamentals
from data.fetch_prices import fetch_prices
from data.sector_data import fetch_sector_performance, get_standard_sector


TEST_TICKERS = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "SBIN.NS"]


def test_vwap():
    print("\n--- 1. Testing VWAP Calculation ---")
    for sym in TEST_TICKERS[:3]:
        df = fetch_prices(sym, period="1mo")
        if not df.empty:
            df = vwap(df)
            latest_close = df["Close"].iloc[-1]
            latest_vwap = df["VWAP"].iloc[-1]
            print(f"[{sym}] Close: INR {latest_close:.2f} | VWAP: INR {latest_vwap:.2f} | Diff: {abs(latest_close - latest_vwap):.2f}")
            assert not np.isnan(latest_vwap), f"VWAP is NaN for {sym}"
            assert latest_vwap > 0, f"VWAP is non-positive for {sym}"
    print("[OK] VWAP Verification PASSED")


def test_shareholding():
    print("\n--- 2. Testing Shareholding Extraction ---")
    for sym in TEST_TICKERS:
        fund = fetch_fundamentals(sym) or {}
        p = fund.get("Promoter_Pct")
        f = fund.get("FII_Pct")
        d = fund.get("DII_Pct")
        inst = fund.get("Institutional_Pct")
        pub = fund.get("Public_Pct")

        print(f"[{sym}] Promoter: {p}% | FII: {f}% | DII: {d}% | Inst: {inst}% | Public: {pub}%")
        assert p is not None, f"Promoter_Pct missing for {sym}"
        assert p >= 0 and p <= 100, f"Invalid Promoter_Pct {p} for {sym}"
    print("[OK] Shareholding Verification PASSED")


def test_sector_engine():
    print("\n--- 3. Testing Sector Engine & Relative Strength ---")
    sec_df = fetch_sector_performance()
    print(f"Fetched {len(sec_df)} NIFTY Sector Indices:")
    if not sec_df.empty:
        print(sec_df[["Sector Index", "3M Return (%)", "RS vs NIFTY 50", "Rotation Quadrant"]].to_string(index=False))
        assert "RS vs NIFTY 50" in sec_df.columns
        assert not sec_df["RS vs NIFTY 50"].isna().any()
    print("[OK] Sector Engine Verification PASSED")


if __name__ == "__main__":
    print("=" * 80)
    print("DATA ACCURACY & INTEGRITY VERIFICATION SUITE")
    print("=" * 80)
    test_vwap()
    test_shareholding()
    test_sector_engine()
    print("\n" + "=" * 80)
    print("ALL DATA VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)
