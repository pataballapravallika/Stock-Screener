import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from data.fetch_prices import fetch_prices
from data.fetch_fundamentals import fetch_fundamentals
from scoring.technical_score import compute_technical_indicators
from fundamentals.piotroski import compute_piotroski_f_score
from fundamentals.altman import compute_altman_z


def calculate_durability_score(fund: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate Trendlyne-style Durability (D) Score (0 to 100).

    Evaluates:
    - ROE & ROCE Quality
    - Debt to Equity Ratio
    - Piotroski F-Score (Financial Stability)
    - Altman Z-Score (Solvency Risk)
    - Revenue & Earnings Growth Consistency
    """
    if not fund:
        return {"score": 45, "grade": "Neutral", "status": "Neutral (Default)"}

    # 1. ROE (25% weight)
    roe = fund.get("ROE") or fund.get("quarterly_roe") or 10.0
    if roe >= 20.0:
        roe_score = 100
    elif roe >= 15.0:
        roe_score = 85
    elif roe >= 10.0:
        roe_score = 65
    elif roe > 0:
        roe_score = 40
    else:
        roe_score = 10

    # 2. Debt to Equity (25% weight)
    de = fund.get("DebtEquity") or fund.get("quarterly_debt_equity")
    if de is None:
        de_score = 70
    elif de <= 0.1:
        de_score = 100
    elif de <= 0.5:
        de_score = 85
    elif de <= 1.0:
        de_score = 60
    elif de <= 1.5:
        de_score = 40
    else:
        de_score = 15

    # 3. Piotroski F-Score (20% weight)
    piot_dict = fund.get("piotroski_f_score") or {}
    piot_val = piot_dict.get("score") if isinstance(piot_dict, dict) else fund.get("PiotroskiFScore")
    if piot_val is None:
        try:
            p_res = compute_piotroski_f_score(fund)
            piot_val = p_res.get("score", 5) if isinstance(p_res, dict) else 5
        except Exception:
            piot_val = 5

    if piot_val >= 7:
        piot_score = 100
    elif piot_val >= 5:
        piot_score = 70
    elif piot_val >= 3:
        piot_score = 45
    else:
        piot_score = 20

    # 4. Altman Z-Score (15% weight)
    alt_dict = fund.get("altman_z_score") or {}
    alt_val = alt_dict.get("score") if isinstance(alt_dict, dict) else fund.get("AltmanZScore")
    if alt_val is None:
        try:
            a_res = compute_altman_z(fund)
            alt_val = a_res.get("score", 2.5) if isinstance(a_res, dict) else 2.5
        except Exception:
            alt_val = 2.5

    if alt_val >= 3.0:
        alt_score = 100
    elif alt_val >= 1.8:
        alt_score = 65
    else:
        alt_score = 20

    # 5. Earnings & Sales Growth Consistency (15% weight)
    rev_g = fund.get("RevenueGrowth") or 0.0
    eps_g = fund.get("EarningsGrowth") or fund.get("EarningsQuarterlyGrowth") or 0.0
    if rev_g > 15 and eps_g > 15:
        growth_score = 95
    elif rev_g > 0 and eps_g > 0:
        growth_score = 75
    elif rev_g > 0 or eps_g > 0:
        growth_score = 50
    else:
        growth_score = 25

    durability = (0.25 * roe_score) + (0.25 * de_score) + (0.20 * piot_score) + (0.15 * alt_score) + (0.15 * growth_score)
    durability = int(round(np.clip(durability, 1, 99)))

    if durability >= 55:
        grade = "Good"
        status = "Strong Financial Quality"
    elif durability >= 35:
        grade = "Neutral"
        status = "Moderate Durability"
    else:
        grade = "Bad"
        status = "High Solvency / Debt Risk"

    return {
        "score": durability,
        "grade": grade,
        "status": status,
        "details": {
            "ROE_Score": roe_score,
            "DebtEquity_Score": de_score,
            "Piotroski_Score": piot_score,
            "Altman_Score": alt_score,
            "Growth_Score": growth_score,
        }
    }


def calculate_valuation_score(fund: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate Trendlyne-style Valuation (V) Score (0 to 100).

    Evaluates:
    - P/E Ratio
    - PEG Ratio
    - Price to Book (P/B)
    - Price to Sales / EV EBITDA
    """
    if not fund:
        return {"score": 45, "grade": "Neutral", "status": "Neutral (Default)"}

    # 1. P/E Ratio (35% weight)
    pe = fund.get("PE")
    if pe is None or pe <= 0:
        pe_score = 45
    elif pe <= 15:
        pe_score = 95
    elif pe <= 25:
        pe_score = 75
    elif pe <= 40:
        pe_score = 50
    elif pe <= 60:
        pe_score = 30
    else:
        pe_score = 15

    # 2. PEG Ratio (35% weight)
    peg = fund.get("PEG")
    if peg is None or peg <= 0:
        peg_score = 50
    elif peg <= 0.8:
        peg_score = 100
    elif peg <= 1.2:
        peg_score = 80
    elif peg <= 1.8:
        peg_score = 55
    elif peg <= 2.5:
        peg_score = 35
    else:
        peg_score = 15

    # 3. Price to Book / Gross Margin (30% weight)
    pb = fund.get("PriceToBook") or fund.get("PriceBook")
    if pb is None or pb <= 0:
        pb_score = 60
    elif pb <= 2.5:
        pb_score = 90
    elif pb <= 5.0:
        pb_score = 70
    elif pb <= 8.0:
        pb_score = 45
    else:
        pb_score = 20

    valuation = (0.35 * pe_score) + (0.35 * peg_score) + (0.30 * pb_score)
    valuation = int(round(np.clip(valuation, 1, 99)))

    if valuation >= 50:
        grade = "Good"
        status = "Attractively Priced / Undervalued"
    elif valuation >= 30:
        grade = "Neutral"
        status = "Fairly Valued"
    else:
        grade = "Bad"
        status = "Expensive / Overvalued"

    return {
        "score": valuation,
        "grade": grade,
        "status": status,
        "details": {
            "PE_Score": pe_score,
            "PEG_Score": peg_score,
            "PB_Score": pb_score,
        }
    }


def calculate_momentum_score(df_prices: pd.DataFrame) -> Dict[str, Any]:
    """Calculate Trendlyne-style Momentum (M) Score (0 to 100).

    Evaluates:
    - RSI (14-day) Range
    - 52-Week High Proximity
    - Moving Average Trend Alignment (Price > 50-DMA > 200-DMA)
    - Volume Trend / Up-day vs Down-day pressure
    """
    if df_prices is None or df_prices.empty or len(df_prices) < 20:
        return {"score": 50, "grade": "Neutral", "status": "Neutral (Default)"}

    if "RSI" not in df_prices.columns or "MA50" not in df_prices.columns:
        df_prices = compute_technical_indicators(df_prices)

    latest = df_prices.iloc[-1]
    close = latest.get("Close", 0.0)

    # 1. RSI (25% weight)
    rsi_val = latest.get("RSI", 50.0)
    if pd.isna(rsi_val):
        rsi_val = 50.0

    if 55 <= rsi_val <= 70:
        rsi_score = 95
    elif 45 <= rsi_val < 55:
        rsi_score = 75
    elif 70 < rsi_val <= 80:
        rsi_score = 65
    elif rsi_val > 80:
        rsi_score = 40
    else:
        rsi_score = 30

    # 2. 52-Week High Proximity (25% weight)
    high_52 = latest.get("High_52W") or df_prices["High"].max()
    dist_52w = (close / high_52) if high_52 and high_52 > 0 else 0.8

    if dist_52w >= 0.95:
        high_score = 100
    elif dist_52w >= 0.85:
        high_score = 85
    elif dist_52w >= 0.75:
        high_score = 60
    elif dist_52w >= 0.65:
        high_score = 40
    else:
        high_score = 20

    # 3. MA Trend Alignment (25% weight)
    ma50 = latest.get("MA50")
    ma200 = latest.get("MA200")

    if pd.notna(ma50) and pd.notna(ma200) and close > ma50 > ma200:
        ma_score = 100
    elif pd.notna(ma200) and close > ma200:
        ma_score = 70
    elif pd.notna(ma50) and close > ma50:
        ma_score = 50
    else:
        ma_score = 20

    # 4. Volume / Price Momentum (25% weight)
    window = df_prices.iloc[-20:]
    vol_ma = latest.get("Volume_MA20") or window["Volume"].mean()
    cur_vol = latest.get("Volume", 0)

    if cur_vol > vol_ma * 1.2 and close > df_prices.iloc[-2]["Close"]:
        vol_score = 95
    elif close > df_prices.iloc[-2]["Close"]:
        vol_score = 75
    else:
        vol_score = 40

    momentum = (0.25 * rsi_score) + (0.25 * high_score) + (0.25 * ma_score) + (0.25 * vol_score)
    momentum = int(round(np.clip(momentum, 1, 99)))

    if momentum >= 59:
        grade = "Good"
        status = "Strong Bullish Trend"
    elif momentum >= 30:
        grade = "Neutral"
        status = "Consolidating / Neutral"
    else:
        grade = "Bad"
        status = "Weak / Bearish Trend"

    return {
        "score": momentum,
        "grade": grade,
        "status": status,
        "details": {
            "RSI_Score": rsi_score,
            "52W_High_Score": high_score,
            "MA_Score": ma_score,
            "Volume_Score": vol_score,
        }
    }


def calculate_trendlyne_dvm(symbol: str, prices: Optional[pd.DataFrame] = None, fund: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Calculate full Trendlyne DVM (Durability, Valuation, Momentum) Scores & Classification.

    Returns:
    - Durability Score & Grade (Good >= 55, Neutral 35-54, Bad < 35)
    - Valuation Score & Grade (Good >= 50, Neutral 30-49, Bad < 30)
    - Momentum Score & Grade (Good >= 59, Neutral 30-58, Bad < 30)
    - Composite DVM Score (0 to 100) & Trendlyne Match Category
    """
    if prices is None or prices.empty:
        prices = fetch_prices(symbol, period="1y")
    if fund is None or not fund:
        fund = fetch_fundamentals(symbol) or {}

    durability = calculate_durability_score(fund)
    valuation = calculate_valuation_score(fund)
    momentum = calculate_momentum_score(prices)

    d_score = durability["score"]
    v_score = valuation["score"]
    m_score = momentum["score"]

    # Trendlyne Composite DVM Formula: 40% Durability, 30% Valuation, 30% Momentum
    dvm_composite = int(round((0.40 * d_score) + (0.30 * v_score) + (0.30 * m_score)))
    dvm_composite = int(np.clip(dvm_composite, 1, 99))

    # Trendlyne Classification
    if durability["grade"] == "Good" and momentum["grade"] == "Good" and dvm_composite >= 60:
        dvm_category = "High DVM (Market Champion)"
        color = "green"
    elif dvm_composite >= 55:
        dvm_category = "Good DVM (Quality Stock)"
        color = "lightgreen"
    elif dvm_composite >= 40:
        dvm_category = "Neutral DVM (Average Performer)"
        color = "orange"
    else:
        dvm_category = "Low DVM (High Risk / Bearish)"
        color = "red"

    return {
        "Symbol": symbol,
        "DVMScore": dvm_composite,
        "DVMCategory": dvm_category,
        "BadgeColor": color,
        "DurabilityScore": d_score,
        "DurabilityGrade": durability["grade"],
        "DurabilityStatus": durability["status"],
        "ValuationScore": v_score,
        "ValuationGrade": valuation["grade"],
        "ValuationStatus": valuation["status"],
        "MomentumScore": m_score,
        "MomentumGrade": momentum["grade"],
        "MomentumStatus": momentum["status"],
        "DurabilityDetails": durability["details"],
        "ValuationDetails": valuation["details"],
        "MomentumDetails": momentum["details"],
    }
