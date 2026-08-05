import sys
sys.path.append(r'd:\career-projects\Stock_Screener')
from data.fetch_fundamentals import fetch_fundamentals
from data.fetch_prices import fetch_prices
import json
symbols=['RELIANCE.NS','TCS.NS','HDFCBANK.NS','SBIN.NS']
for s in symbols:
    f=fetch_fundamentals(s)
    prices=fetch_prices(s, period='1y')
    out={
        'symbol': s,
        'SharesOutstanding': f.get('SharesOutstanding'),
        'FloatShares': f.get('FloatShares'),
        'ROE': f.get('ROE'),
        'ROCE': f.get('ROCE'),
        'MarketCap': f.get('MarketCap'),
        'PriceSample': (prices['Close'].iloc[-1] if not prices.empty else None)
    }
    print(json.dumps(out, default=str, indent=2))
