import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.fetch_fundamentals import fetch_fundamentals, clear_fundamentals_cache
from scoring.fundamental_score import score_fundamental

clear_fundamentals_cache()
symbols = ['RELIANCE.NS', 'TCS.NS', 'INFY.NS', 'HDFCBANK.NS', 'SBIN.NS']
for s in symbols:
    f = fetch_fundamentals(s)
    fund_for_scoring = {
        "EPS_Growth": f.get("EarningsGrowth"),
        "Revenue_Growth": f.get("RevenueGrowth"),
        "PAT_Growth": f.get("PAT_YoY"),
        "ROE": f.get("ROE"),
        "ROCE": f.get("ROCE"),
        "ROA": f.get("ROA"),
        "Debt_Equity": f.get("DebtEquity"),
        "Piotroski_FScore": f.get("Piotroski_FScore"),
        "Altman_ZScore": f.get("Altman_ZScore"),
    }
    result = score_fundamental(fund_for_scoring)
    print(f"\n{s} ({f.get('fundamentals_source', 'unknown')}):")
    print(f"  Available keys: {sorted([k for k,v in fund_for_scoring.items() if v is not None and not (isinstance(v, float) and str(v)=='nan')])}")
    print(f"  Score: {result['score']}/{result['max_score']} = {result['percentage']}%")
    print(f"  Signal: {result['signal']}")
    print(f"  Unavailable: {result['unavailable']}")
