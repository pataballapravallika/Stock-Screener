import sys
sys.path.insert(0, r'D:\career-projects\Stock_Screener')

print('=== Final Verification ===')

# 1. Test fetch_fundamentals
from data.fetch_fundamentals import fetch_fundamentals
fund = fetch_fundamentals('RELIANCE.NS')
print(f'ROE: {fund.get("ROE")}')
print(f'ROCE: {fund.get("ROCE")}')
print(f'ROA: {fund.get("ROA")}')
print(f'OCF Annual: {fund.get("OperatingCashFlowAnnual")}')
print(f'FCF Annual: {fund.get("FreeCashFlowAnnual")}')
print(f'FCF TTM: {fund.get("FreeCashFlowTTM")}')
print(f'Quarterly available: {fund.get("quarterly_financials") is not None}')

# 2. Test all page imports
pages = [
    'home', 'pages.1_Dashboard', 'pages.2_Growth_Analysis',
    'pages.3_Quality_Analysis', 'pages.4_Ownership_Analysis', 'pages.5_Technical_Analysis',
    'pages.6_Valuation', 'pages.7_Catalysts', 'pages.8_Backtesting',
    'pages.9_Portfolio_Risk', 'pages.10_Sector_Rotation', 'pages.11_Ranking_Engine',
    'pages.12_Alerts_AI',
]
all_ok = True
for p in pages:
    try:
        __import__(p)
        print(f'OK: {p}')
    except Exception as e:
        print(f'FAIL: {p} - {e}')
        all_ok = False

if all_ok:
    print('All 13 pages import successfully')

print('=== Verification Complete ===')