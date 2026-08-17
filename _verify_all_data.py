"""Verification script for price and fundamental fetching."""
from data.fetch_fundamentals import fetch_fundamentals
from data.fetch_prices import fetch_prices

symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "TATAMOTORS", "SBIN", "WIPRO", "HCLTECH"]

print("Testing price and fundamental fetching for all universe tickers...\n")
for sym in symbols:
    prices = fetch_prices(sym, "5d")
    fund = fetch_fundamentals(sym)
    price_len = len(prices) if not prices.empty else 0
    last_price = f"Rs.{prices['Close'].iloc[-1]:.2f}" if price_len > 0 else "N/A"
    rev = fund.get("Revenue")
    pat = fund.get("PAT")
    eps = fund.get("EPS")
    status = fund.get("data_verification_status")
    source = fund.get("fundamentals_source")
    print(f"[{sym}]")
    print(f"   Price Data  : {price_len} rows returned (Close: {last_price})")
    print(f"   Fundamentals: Revenue=Rs.{rev} Cr, PAT=Rs.{pat} Cr, EPS={eps}")
    print(f"   Verification: status={status}, source={source}\n")
