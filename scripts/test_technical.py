from data.fetch_prices import fetch_prices
from scoring.technical_score import compute_technical_indicators, score_technical

symbol = 'RELIANCE.NS'
df = fetch_prices(symbol, period='1y')
if df.empty:
    print('No price data')
else:
    df2 = compute_technical_indicators(df)
    latest = df2.iloc[-1]
    res = score_technical(latest)
    print('EMA values:')
    for c in ['EMA9','EMA21','EMA50','EMA100','EMA150','EMA200']:
        print(c, latest.get(c))
    print('EMA alignment:', res['conditions'].get('ema_alignment'))
    print('Technical percentage:', res['percentage'])
