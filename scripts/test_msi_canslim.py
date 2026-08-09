#!/usr/bin/env python3
"""Verification Script for MarketSmith India (MSI) CANSLIM Ratings & Master Score Engine."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.msi_canslim import calculate_msi_ratings

TEST_TICKERS = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"]


def test_msi_engine():
    print("=" * 80)
    print("MARKETSMITH INDIA (MSI) CANSLIM ENGINE TEST")
    print("=" * 80)

    for sym in TEST_TICKERS:
        msi = calculate_msi_ratings(sym)
        print(f"[{sym}]")
        print(f"  Master Score : {msi['MasterScore']}/99 ({msi['MasterGrade']})")
        print(f"  EPS Rating   : {msi['EPSRating']}/99")
        print(f"  RS Rating    : {msi['RSRating']}/99")
        print(f"  Buyer Demand : {msi['BuyerDemandGrade']} ({msi['BuyerDemandStatus']})")
        print(f"  Sponsorship  : Grade {msi['SponsorshipGrade']} ({msi['InstitutionalPct']}% Inst.)")
        print("-" * 50)

        assert 1 <= msi["MasterScore"] <= 99, f"Invalid MasterScore for {sym}"
        assert 1 <= msi["EPSRating"] <= 99, f"Invalid EPSRating for {sym}"
        assert 1 <= msi["RSRating"] <= 99, f"Invalid RSRating for {sym}"
        assert msi["BuyerDemandGrade"] in ["A+", "A", "A-", "B", "C", "D", "E"]

    print("[OK] All MarketSmith India CANSLIM rating tests PASSED!")
    print("=" * 80)


if __name__ == "__main__":
    test_msi_engine()
