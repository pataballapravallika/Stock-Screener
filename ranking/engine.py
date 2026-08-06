from typing import List, Dict
import pandas as pd
from data.fetch_prices import fetch_prices
from data.fetch_fundamentals import fetch_fundamentals
from scoring.technical_score import compute_technical_indicators, score_technical
from scoring.fundamental_score import score_fundamental
from scoring.combined_score import combined_score


def rank_symbols(symbols: List[str]) -> pd.DataFrame:
    rows = []
    for symbol in symbols:
        try:
            prices = fetch_prices(symbol, period="1y")
            if prices.empty:
                continue
            df = compute_technical_indicators(prices)
            latest = df.iloc[-1]
            tech_res = score_technical(latest)
        except Exception:
            tech_res = {"percentage": 0.0}

        try:
            fund = fetch_fundamentals(symbol) or {}
            fund_for_scoring = {
                "EPS_Growth": fund.get("EarningsGrowth"),
                "Revenue_Growth": fund.get("RevenueGrowth"),
                "PAT_Growth": fund.get("PAT_Growth"),
                "ROE": fund.get("ROE"),
                "ROCE": fund.get("ROCE"),
                "ROA": fund.get("ROA"),
                "Debt_Equity": fund.get("DebtEquity"),
            }
            fund_res = score_fundamental(fund_for_scoring)
        except Exception:
            fund_res = {"percentage": 0.0}

        combined = combined_score(technical_result=tech_res, fundamental_result=fund_res, is_bank=False)

        rows.append({
            "Symbol": symbol,
            "Company": fund.get("Company") if fund else None,
            "Technical": tech_res.get("percentage", 0.0),
            "Fundamental": fund_res.get("percentage", 0.0),
            "Combined": combined.get("combined_percentage", 0.0),
        })

    df_out = pd.DataFrame(rows)
    if df_out.empty:
        return df_out
    df_out = df_out.sort_values("Combined", ascending=False).reset_index(drop=True)
    df_out.insert(0, "Rank", df_out.index + 1)
    return df_out
