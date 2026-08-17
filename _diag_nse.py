"""Diagnostic script to test NSE API connectivity."""
import requests
import json
import time

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

session = requests.Session()
session.headers.update(headers)

# Step 1: Visit homepage to get cookies
print("Step 1: Visiting NSE homepage...")
try:
    resp = session.get("https://www.nseindia.com/", timeout=15)
    print(f"  Status: {resp.status_code}, Cookies: {len(session.cookies)}")
    for c in session.cookies:
        print(f"  Cookie: {c.name}")
except Exception as e:
    print(f"  ERROR: {e}")

time.sleep(1)

# Step 2: Visit a secondary page
print("Step 2: Visiting live equity market...")
try:
    resp2 = session.get("https://www.nseindia.com/market-data/live-equity-market", timeout=15)
    print(f"  Status: {resp2.status_code}")
except Exception as e:
    print(f"  ERROR: {e}")

time.sleep(1)

# Step 3: Try the API with proper Referer
print("Step 3: Trying quote-equity API...")
try:
    resp3 = session.get(
        "https://www.nseindia.com/api/quote-equity?symbol=RELIANCE",
        headers={"Accept": "application/json, text/plain, */*", "Referer": "https://www.nseindia.com/get-quotes/equity?symbol=RELIANCE"},
        timeout=15,
    )
    print(f"  Status: {resp3.status_code}")
    if resp3.status_code == 200:
        data = resp3.json()
        info = data.get("info", {})
        print(f"  Company: {info.get('companyName')}")
        print(f"  Sector: {data.get('industryInfo', {}).get('macro')}")
    else:
        print(f"  Body: {resp3.text[:300]}")
except Exception as e:
    print(f"  ERROR: {e}")

time.sleep(0.5)

# Step 4: Try corporate-announcements API
print("Step 4: Trying corporate-announcements API...")
try:
    resp4 = session.get(
        "https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=RELIANCE&subCategory=financial-results",
        headers={"Accept": "application/json", "Referer": "https://www.nseindia.com/"},
        timeout=15,
    )
    print(f"  Status: {resp4.status_code}")
    if resp4.status_code == 200:
        data4 = resp4.json()
        print(f"  Type: {type(data4).__name__}, Length: {len(data4) if isinstance(data4, list) else 'dict'}")
        if isinstance(data4, list) and data4:
            rec = data4[0]
            print(f"  First item keys: {list(rec.keys())[:10]}")
            print(f"  hasXbrl: {rec.get('hasXbrl')}")
            print(f"  attchmntText: {str(rec.get('attchmntText', ''))[:100]}")
    else:
        print(f"  Body: {resp4.text[:300]}")
except Exception as e:
    print(f"  ERROR: {e}")

# Step 5: Check nse_xbrl package
print("\nStep 5: Checking nse_xbrl package...")
try:
    from nse_xbrl import NSEClient
    print("  nse_xbrl package is installed")
    client = NSEClient()
    print("  NSEClient created successfully")
except ImportError:
    print("  nse_xbrl package NOT installed - will use builtin HTTP fallback")
except Exception as e:
    print(f"  nse_xbrl error: {e}")

# Step 6: Check database for existing data
print("\nStep 6: Checking database for cached data...")
try:
    from data.database import get_latest_quarterly_reports, get_latest_annual_reports, init_db
    init_db()
    for sym in ["RELIANCE", "TCS", "INFY", "HDFCBANK"]:
        q_df = get_latest_quarterly_reports(sym, limit=1)
        a_df = get_latest_annual_reports(sym, limit=1)
        q_count = len(q_df) if not q_df.empty else 0
        a_count = len(a_df) if not a_df.empty else 0
        if q_count or a_count:
            print(f"  {sym}: {q_count} quarterly, {a_count} annual records")
            if not q_df.empty:
                row = q_df.iloc[0]
                print(f"    Latest Q: date={row.get('report_date')}, rev={row.get('revenue')}, pat={row.get('pat')}, source={row.get('source_type')}")
        else:
            print(f"  {sym}: NO cached data")
except Exception as e:
    print(f"  DB error: {e}")
