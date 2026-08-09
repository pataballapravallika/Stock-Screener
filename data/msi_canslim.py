import pandas as pd
import numpy as np
from typing import Dict, Any
from data.fetch_prices import fetch_prices
from data.fetch_fundamentals import fetch_fundamentals


def compute_rs_rating(df_prices: pd.DataFrame) -> int:
    """Calculate MarketSmith Relative Strength (RS Rating: 1 to 99).
    Formula: RS_raw = 0.4 * R_1Q + 0.2 * R_2Q + 0.2 * R_3Q + 0.2 * R_4Q
    """
    if df_prices is None or df_prices.empty or len(df_prices) < 20:
        return 50

    closes = df_prices["Close"]
    p_cur = closes.iloc[-1]

    p_1q = closes.iloc[-63] if len(closes) >= 63 else closes.iloc[0]
    p_2q = closes.iloc[-126] if len(closes) >= 126 else closes.iloc[0]
    p_3q = closes.iloc[-189] if len(closes) >= 189 else closes.iloc[0]
    p_4q = closes.iloc[0]

    r1 = ((p_cur - p_1q) / p_1q) * 100
    r2 = ((p_1q - p_2q) / p_2q) * 100
    r3 = ((p_2q - p_3q) / p_3q) * 100
    r4 = ((p_3q - p_4q) / p_4q) * 100

    raw_rs = (0.4 * r1) + (0.2 * r2) + (0.2 * r3) + (0.2 * r4)

    # Scale raw RS to 1-99 percentile range (centered around 0% = 50 RS)
    scaled_rs = int(round(50 + (raw_rs * 0.8)))
    return int(np.clip(scaled_rs, 1, 99))


def compute_eps_rating(fund: Dict[str, Any]) -> int:
    """Calculate MarketSmith EPS Rating (1 to 99).
    Evaluates latest EPS YoY growth %, Sales YoY growth %, and ROE.
    """
    if not fund:
        return 50

    eps_yoy = fund.get("EPS_YoY") or fund.get("EarningsQuarterlyGrowth") or fund.get("EarningsGrowth") or fund.get("PAT_YoY") or fund.get("EPS_QoQ") or 0.0
    sales_yoy = fund.get("Sales_YoY") or fund.get("RevenueGrowth") or fund.get("Sales_QoQ") or 0.0
    roe = fund.get("ROE") or 10.0

    raw_eps_score = (eps_yoy * 0.5) + (sales_yoy * 0.3) + (roe * 0.2)
    scaled_eps = int(round(50 + (raw_eps_score * 0.6)))
    return int(np.clip(scaled_eps, 1, 99))


def compute_buyer_demand(df_prices: pd.DataFrame) -> Dict[str, Any]:
    """Calculate Accumulation/Distribution (A/D Grade) based on 13-week volume vs price trend.
    Grades: A+, A, A-, B, C, D, E
    """
    if df_prices is None or df_prices.empty or len(df_prices) < 15:
        return {"grade": "C", "ratio": 1.0, "status": "Neutral"}

    window = df_prices.iloc[-65:] if len(df_prices) >= 65 else df_prices
    changes = window["Close"].diff()
    vols = window["Volume"]

    up_vol = vols[changes > 0].sum()
    down_vol = vols[changes < 0].sum()

    if down_vol == 0 or pd.isna(down_vol):
        ratio = 1.5
    else:
        ratio = float(up_vol / down_vol)

    if ratio >= 1.5:
        grade, status = "A+", "Heavy Accumulation"
    elif ratio >= 1.3:
        grade, status = "A", "Strong Accumulation"
    elif ratio >= 1.15:
        grade, status = "A-", "Moderate Accumulation"
    elif ratio >= 1.05:
        grade, status = "B", "Buying Pressure"
    elif ratio >= 0.95:
        grade, status = "C", "Neutral"
    elif ratio >= 0.80:
        grade, status = "D", "Selling Pressure"
    else:
        grade, status = "E", "Heavy Distribution"

    return {"grade": grade, "ratio": round(ratio, 2), "status": status}


def compute_sponsorship_rating(fund: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate Institutional Sponsorship Rating (A, B, C, D) based on FII + DII holding %."""
    if not fund:
        return {"grade": "C", "total_inst": 0.0}

    fii = fund.get("FII_Pct") or 0.0
    dii = fund.get("DII_Pct") or 0.0
    total_inst = fund.get("Institutional_Pct") or fund.get("InstitutionsPercentHeld") or (fii + dii)

    if total_inst >= 45:
        grade = "A"
    elif total_inst >= 25:
        grade = "B"
    elif total_inst >= 10:
        grade = "C"
    else:
        grade = "D"

    return {"grade": grade, "total_inst": round(total_inst, 2)}


def calculate_msi_ratings(symbol: str, prices: pd.DataFrame = None, fund: Dict[str, Any] = None) -> Dict[str, Any]:
    """Calculate full MarketSmith India (MSI) CANSLIM Ratings for a given symbol."""
    if prices is None or prices.empty:
        prices = fetch_prices(symbol, period="1y")
    if fund is None or not fund:
        fund = fetch_fundamentals(symbol) or {}

    rs_rating = compute_rs_rating(prices)
    eps_rating = compute_eps_rating(fund)
    buyer_demand = compute_buyer_demand(prices)
    sponsorship = compute_sponsorship_rating(fund)

    ad_numeric = {"A+": 95, "A": 90, "A-": 85, "B": 75, "C": 50, "D": 35, "E": 20}.get(buyer_demand["grade"], 50)
    spon_numeric = {"A": 90, "B": 75, "C": 50, "D": 30}.get(sponsorship["grade"], 50)

    # Master Score (0-99 Composite Rating)
    master_score = int(round(
        (0.35 * eps_rating) +
        (0.35 * rs_rating) +
        (0.15 * ad_numeric) +
        (0.15 * spon_numeric)
    ))
    master_score = int(np.clip(master_score, 1, 99))

    if master_score >= 85:
        master_grade = "A+ (Market Leader)"
    elif master_score >= 75:
        master_grade = "A (Strong Outperformer)"
    elif master_score >= 65:
        master_grade = "B (Growth Stock)"
    elif master_score >= 50:
        master_grade = "C (Average)"
    else:
        master_grade = "D/E (Laggard)"

    return {
        "Symbol": symbol,
        "MasterScore": master_score,
        "MasterGrade": master_grade,
        "EPSRating": eps_rating,
        "RSRating": rs_rating,
        "BuyerDemandGrade": buyer_demand["grade"],
        "BuyerDemandStatus": buyer_demand["status"],
        "SponsorshipGrade": sponsorship["grade"],
        "InstitutionalPct": sponsorship["total_inst"],
        "PromoterPct": fund.get("Promoter_Pct"),
    }
