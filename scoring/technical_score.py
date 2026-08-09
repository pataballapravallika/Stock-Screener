import pandas as pd
import numpy as np
from indicators.momentum import rsi, macd
from indicators.trend import moving_averages, high_52_week, breakout as calc_breakout, bollinger_bands, vwap
from indicators.trend import breakout_status
from indicators.volatility import supertrend, adr
from scoring.config import (
    ScoringConfig,
    TechnicalConfig,
    DEFAULT_CONFIG,
    DEFAULT_TECHNICAL_CONFIG,
)


def compute_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df = moving_averages(df)
    df["RSI"] = rsi(df["Close"])
    df["MACD"], df["MACD_Signal"], df["MACD_Hist"] = macd(df["Close"])
    df = high_52_week(df)
    df = calc_breakout(df)
    df = breakout_status(df)
    df = bollinger_bands(df)
    df = adr(df)
    df = supertrend(df)

    df = vwap(df)

    low14 = df["Low"].rolling(14).min()
    high14 = df["High"].rolling(14).max()
    denominator = high14 - low14
    df["Stochastic_K"] = np.where(denominator != 0, ((df["Close"] - low14) / denominator) * 100, np.nan)
    df["Stochastic_D"] = df["Stochastic_K"].rolling(3).mean()

    previous_close = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        abs(df["High"] - previous_close),
        abs(df["Low"] - previous_close)
    ], axis=1).max(axis=1)
    df["ATR"] = tr.ewm(alpha=1/14, adjust=False).mean()

    df["Volume_MA20"] = df["Volume"].rolling(20).mean()

    return df


def score_technical(
    row: pd.Series,
    config: Optional[ScoringConfig] = None,
    tc: Optional[TechnicalConfig] = None,
) -> dict:
    if config is None:
        config = DEFAULT_CONFIG
    if tc is None:
        tc = DEFAULT_TECHNICAL_CONFIG

    score = 0
    max_score = 0
    conditions = {}

    ma200 = row.get("MA200")
    ma50 = row.get("MA50")
    close = row.get("Close")
    rsi_val = row.get("RSI")
    macd_line = row.get("MACD")
    macd_signal = row.get("MACD_Signal")
    dist_52w = row.get("Distance_52W_High")
    breakout = row.get("Breakout", False)
    volume = row.get("Volume")
    volume_ma20 = row.get("Volume_MA20")
    supertrend = row.get("SuperTrend")

    # EMA alignment: check if shorter EMAs are above longer EMAs (9 > 21 > 50 > 100 > 150 > 200)
    ema_cols = ["EMA9", "EMA21", "EMA50", "EMA100", "EMA150", "EMA200"]
    ema_vals = [row.get(c) for c in ema_cols]
    ema_alignment = None
    try:
        if all(v is not None for v in ema_vals):
            ema_alignment = all(ema_vals[i] > ema_vals[i+1] for i in range(len(ema_vals)-1))
    except Exception:
        ema_alignment = None

    if config.use_ma_trend:
        max_score += tc.price_above_ma200_weight
        if pd.notna(ma200) and pd.notna(close) and close > ma200:
            score += tc.price_above_ma200_weight
            conditions["price_above_ma200"] = True
        else:
            conditions["price_above_ma200"] = False

        max_score += tc.ma50_above_ma200_weight
        if pd.notna(ma50) and pd.notna(ma200) and ma50 > ma200:
            score += tc.ma50_above_ma200_weight
            conditions["ma50_above_ma200"] = True
        else:
            conditions["ma50_above_ma200"] = False

        max_score += tc.above_ma50_weight
        if pd.notna(ma50) and pd.notna(close) and close > ma50:
            score += tc.above_ma50_weight
            conditions["price_above_ma50"] = True
        else:
            conditions["price_above_ma50"] = False

    max_score += tc.rsi_range_weight
    if pd.notna(rsi_val) and config.rsi_min <= rsi_val <= config.rsi_max:
        score += tc.rsi_range_weight
        conditions["rsi_in_range"] = True
    else:
        conditions["rsi_in_range"] = False

    if config.use_macd:
        max_score += tc.macd_bullish_weight
        if pd.notna(macd_line) and pd.notna(macd_signal) and macd_line > macd_signal:
            score += tc.macd_bullish_weight
            conditions["macd_bullish"] = True
        else:
            conditions["macd_bullish"] = False

    max_score += tc.near_52w_high_weight
    if pd.notna(dist_52w) and dist_52w >= config.max_52w_distance:
        score += tc.near_52w_high_weight
        conditions["near_52w_high"] = True
    else:
        conditions["near_52w_high"] = False

    if config.use_breakout:
        max_score += tc.breakout_weight
        if breakout:
            score += tc.breakout_weight
            conditions["breakout"] = True
        else:
            conditions["breakout"] = False

    if config.use_volume:
        max_score += tc.volume_above_avg_weight
        if (
            pd.notna(volume)
            and pd.notna(volume_ma20)
            and volume_ma20 > 0
            and volume > volume_ma20
        ):
            score += tc.volume_above_avg_weight
            conditions["volume_above_avg"] = True
        else:
            conditions["volume_above_avg"] = False

    if config.use_supertrend:
        max_score += tc.supertrend_bullish_weight
        if pd.notna(supertrend) and supertrend == 1:
            score += tc.supertrend_bullish_weight
            conditions["supertrend_bullish"] = True
        else:
            conditions["supertrend_bullish"] = False

    # expose EMA alignment as an informational condition (no weight added by default)
    conditions["ema_alignment"] = True if ema_alignment else False

    percentage = (score / max_score * 100) if max_score > 0 else 0.0

    if percentage >= config.buy_threshold:
        signal = "BUY"
    elif percentage >= config.sell_threshold:
        signal = "HOLD"
    else:
        signal = "SELL"

    return {
        "score": score,
        "max_score": max_score,
        "percentage": round(percentage, 2),
        "signal": signal,
        "conditions": conditions,
    }


def get_signal_explanation(conditions: dict, signal: str) -> str:
    parts = []
    if signal == "BUY":
        parts.append("Technical conditions are bullish.")
    elif signal == "SELL":
        parts.append("Technical conditions are bearish.")
    else:
        parts.append("Technical conditions are neutral.")

    bull = [k for k, v in conditions.items() if v]
    bear = [k for k, v in conditions.items() if not v]

    if bull:
        parts.append(f"Bullish: {', '.join(bull)}.")
    if bear:
        parts.append(f"Bearish/Neutral: {', '.join(bear)}.")

    return " ".join(parts)
