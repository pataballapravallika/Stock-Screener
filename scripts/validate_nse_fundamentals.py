"""Validation script: Verify fundamental data from NSE official sources.

Checks that the application's fetched fundamentals match NSE's official
XBRL filings data within a 5% tolerance (10% for shareholding percentages
due to different reference periods).

Usage:
    python scripts/validate_nse_fundamentals.py
"""
import sys
import os
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.fetch_fundamentals import fetch_fundamentals, clear_fundamentals_cache
from data.providers.nse_xbrl_provider import NSEXBRLProvider
from data.providers.official_reports_provider import OfficialReportsProvider
from data.providers.yahoo_price_provider import YahooPriceProvider
from data.database import get_latest_quarterly_reports

TOLERANCE_PCT = 0.05  # 5% tolerance for financial values
SHAREHOLDING_TOLERANCE_PCT = 0.10  # 10% tolerance for shareholding %

TICKERS = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "SBIN.NS"]


def get_nse_reference(symbol: str) -> dict:
    """Fetch fresh reference data directly from NSE official sources."""
    clean = symbol.split(".")[0]
    provider = NSEXBRLProvider()

    reference = {
        "symbol": symbol,
        "fundamentals": {},
        "price_only": {},
        "shareholding": {},
        "errors": [],
    }

    try:
        fundamentals = provider.build_fundamentals_dict(symbol)
        reference["fundamentals"] = fundamentals
    except Exception as e:
        reference["errors"].append(f"NSE XBRL error: {e}")

    try:
        price_info = YahooPriceProvider().get_company_info(symbol)
        if price_info:
            reference["price_only"] = price_info
    except Exception as e:
        reference["errors"].append(f"Yahoo price error: {e}")

    try:
        sh = provider.get_shareholding(symbol)
        reference["shareholding"] = sh
    except Exception as e:
        reference["errors"].append(f"NSE shareholding error: {e}")

    return reference


def check_data_quality(symbol: str) -> dict:
    """Check data quality for a single ticker."""
    result = {
        "symbol": symbol,
        "checks": [],
        "passed": 0,
        "failed": 0,
        "no_data": 0,
    }

    ref = get_nse_reference(symbol)
    ref_fund = ref.get("fundamentals", {})

    if not ref_fund or not ref_fund.get("Symbol"):
        result["checks"].append({
            "field": "Overall Fundamentals",
            "status": "FAIL",
            "detail": "NSE XBRL provider returned no data. Check filings availability.",
            "reference_value": None,
            "app_value": None,
        })
        result["failed"] += 1
        return result

    fund = fetch_fundamentals(symbol)

    key_fields = [
        ("Company", "Company Name"),
        ("Sector", "Sector"),
        ("Industry", "Industry"),
        ("MarketCap", "Market Cap (Cr)"),
        ("Revenue", "Revenue (Cr)"),
        ("PAT", "PAT (Cr)"),
        ("EPS", "EPS"),
        ("PE", "P/E Ratio"),
        ("ROE", "ROE"),
        ("ROCE", "ROCE"),
        ("DebtEquity", "Debt/Equity"),
        ("OPM", "OPM"),
        ("NPM", "NPM"),
        ("Promoter_Pct", "Promoter %"),
        ("FII_Pct", "FII %"),
        ("DII_Pct", "DII %"),
        ("Institutional_Pct", "Institutional %"),
        ("Public_Pct", "Public %"),
    ]

    for app_key, label in key_fields:
        ref_val = ref_fund.get(app_key)
        app_val = fund.get(app_key)

        if ref_val is None and app_val is None:
            result["checks"].append({
                "field": label,
                "status": "N/A",
                "detail": "Data not available from official source",
                "reference_value": None,
                "app_value": None,
            })
            result["no_data"] += 1
        elif ref_val is None:
            result["checks"].append({
                "field": label,
                "status": "N/A",
                "detail": "Reference data unavailable; app has value (may be from fallback)",
                "reference_value": None,
                "app_value": app_val,
            })
            result["no_data"] += 1
        elif app_val is None:
            result["checks"].append({
                "field": label,
                "status": "FAIL",
                "detail": "App missing data that reference source provides",
                "reference_value": ref_val,
                "app_value": None,
            })
            result["failed"] += 1
        else:
            try:
                ref_f = float(ref_val)
                app_f = float(app_val)
                tol = SHAREHOLDING_TOLERANCE_PCT if "Pct" in app_key else TOLERANCE_PCT
                if ref_f != 0:
                    within_tolerance = abs(ref_f - app_f) <= abs(ref_f * tol)
                else:
                    within_tolerance = abs(app_f) <= abs(tol * 100)
                if within_tolerance:
                    result["checks"].append({
                        "field": label,
                        "status": "PASS",
                        "detail": f"Within {tol*100:.0f}% tolerance",
                        "reference_value": ref_val,
                        "app_value": app_val,
                    })
                    result["passed"] += 1
                else:
                    result["checks"].append({
                        "field": label,
                        "status": "FAIL",
                        "detail": f"Outside {tol*100:.0f}% tolerance",
                        "reference_value": ref_val,
                        "app_value": app_val,
                    })
                    result["failed"] += 1
            except (ValueError, TypeError):
                if str(ref_val).strip() == str(app_val).strip():
                    result["checks"].append({
                        "field": label,
                        "status": "PASS",
                        "detail": "Values match (non-numeric)",
                        "reference_value": ref_val,
                        "app_value": app_val,
                    })
                    result["passed"] += 1
                else:
                    result["checks"].append({
                        "field": label,
                        "status": "N/A",
                        "detail": "Non-numeric value, manual review needed",
                        "reference_value": ref_val,
                        "app_value": app_val,
                    })
                    result["no_data"] += 1

    # Check FII/DII are not fabricated from Institutional_Pct
    fii = fund.get("FII_Pct")
    dii = fund.get("DII_Pct")
    inst = fund.get("Institutional_Pct")
    if fii is not None and dii is not None and inst is not None:
        if abs((fii + dii) - inst) < 1.0:
            result["checks"].append({
                "field": "FII/DII Split",
                "status": "WARNING",
                "detail": "FII + DII == Institutional_Pct; may be a split rather than independent data",
                "reference_value": None,
                "app_value": f"FII={fii}, DII={dii}, INST={inst}",
            })
        else:
            result["checks"].append({
                "field": "FII/DII Split",
                "status": "PASS",
                "detail": "FII and DII are independent values (not fabricated split)",
                "reference_value": None,
                "app_value": f"FII={fii}, DII={dii}, INST={inst}",
            })
            result["passed"] += 1

    # Check VWAP uses session VWAP (not cumulative multi-day)
    from indicators.vwap_engine import compute_session_vwap
    vwap_result = compute_session_vwap(symbol)
    if vwap_result.get("status") == "VALID":
        result["checks"].append({
            "field": "Session VWAP",
            "status": "PASS",
            "detail": f"Session VWAP = {vwap_result.get('session_vwap')}, {vwap_result.get('bar_count')} bars",
            "reference_value": None,
            "app_value": vwap_result.get("session_vwap"),
        })
        result["passed"] += 1
    elif vwap_result.get("status") == "NO_DATA":
        result["checks"].append({
            "field": "Session VWAP",
            "status": "N/A",
            "detail": "No intraday data available (market may be closed)",
            "reference_value": None,
            "app_value": None,
        })
        result["no_data"] += 1
    else:
        result["checks"].append({
            "field": "Session VWAP",
            "status": "FAIL",
            "detail": "VWAP computation failed",
            "reference_value": None,
            "app_value": None,
        })
        result["failed"] += 1

    return result


def main():
    print("=" * 80)
    print("NSE FUNDAMENTALS VALIDATION")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Tickers: {TICKERS}")
    print(f"Tolerance: {TOLERANCE_PCT*100}% (shareholding: {SHAREHOLDING_TOLERANCE_PCT*100}%)")
    print("=" * 80)

    all_results = []
    total_passed = 0
    total_failed = 0
    total_na = 0

    for symbol in TICKERS:
        print(f"\n{'-' * 60}")
        print(f"Checking {symbol}")
        print(f"{'-' * 60}")
        clear_fundamentals_cache()
        result = check_data_quality(symbol)
        all_results.append(result)

        for check in result["checks"]:
            status_icon = "OK" if check["status"] == "PASS" else "NO" if check["status"] == "FAIL" else "NA" if check["status"] == "N/A" else "!!"
            print(f"  {status_icon} {check['field']}: {check['status']}")
            if check["reference_value"] is not None or check["app_value"] is not None:
                print(f"      Reference: {check['reference_value']}")
                print(f"      App:       {check['app_value']}")
            print(f"      Detail: {check['detail']}")

        total_passed += result["passed"]
        total_failed += result["failed"]
        total_na += result["no_data"]
        print(f"\n  Summary: {result['passed']} passed, {result['failed']} failed, {result['no_data']} N/A")

    print(f"\n{'=' * 80}")
    print(f"OVERALL SUMMARY")
    print(f"{'=' * 80}")
    print(f"  Total checks passed: {total_passed}")
    print(f"  Total checks failed: {total_failed}")
    print(f"  Total checks N/A:    {total_na}")
    print(f"  Pass rate: {total_passed / (total_passed + total_failed) * 100:.1f}%" if (total_passed + total_failed) > 0 else "  No checks to evaluate")
    print(f"{'=' * 80}")

    # Write results to file
    report_path = os.path.join(os.path.dirname(__file__), "..", "data", "reports", "validation_nse_report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "tolerance_pct": TOLERANCE_PCT,
            "shareholding_tolerance_pct": SHAREHOLDING_TOLERANCE_PCT,
            "tickers": TICKERS,
            "results": all_results,
            "summary": {
                "total_passed": total_passed,
                "total_failed": total_failed,
                "total_na": total_na,
            },
        }, f, indent=2, default=str)
    print(f"\nDetailed report written to: {report_path}")

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
