def technical_score(row):

    score = 0

    if row["Close"] > row["MA200"]:
        score += 20

    if row["MA50"] > row["MA200"]:
        score += 15

    if 50 <= row["RSI"] <= 70:
        score += 15

    if row["MACD"] > row["MACD_Signal"]:
        score += 15

    if row["Distance_52W_High"] >= -10:
        score += 15

    if row.get("Breakout", False):
        score += 10

    if row.get("SuperTrend", -1) == 1:
        score += 10

    return score


def fundamental_score(f):

    score = 0

    revenue = f.get("RevenueGrowth")
    earnings = f.get("EarningsGrowth")
    roe = f.get("ROE")
    pe = f.get("PE")
    debt = f.get("DebtEquity")

    if revenue is not None and revenue > 0.10:
        score += 20

    if earnings is not None and earnings > 0.10:
        score += 20

    if roe is not None and roe > 0.15:
        score += 20

    if pe is not None and 0 < pe < 30:
        score += 20

    # Yahoo often reports debt/equity as percentage-like values.
    if debt is not None and debt < 100:
        score += 20

    return score


def final_score(technical, fundamental):
    return (
        technical * 0.60 +
        fundamental * 0.40
    )