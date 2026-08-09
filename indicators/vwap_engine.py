"""Intraday Session VWAP Engine.

Computes exact intraday session VWAP for the current trading day using
5-minute intraday bars fetched from yfinance.

Session VWAP = Sum(Typical_Price * Intraday_Volume) / Sum(Intraday_Volume)
where Typical_Price = (High + Low + Close) / 3 for each intraday bar.
"""

from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
import yfinance as yf


def compute_session_vwap(symbol: str) -> Dict[str, Any]:
    """Fetch 5-minute intraday bars for current session and compute exact Session VWAP.

    Returns:
        dict with:
          - session_vwap: float
          - latest_close: float
          - vwap_diff: float (latest_close - session_vwap)
          - vwap_diff_pct: float
          - bar_count: int
          - timeframe: "5m Session"
          - status: "VALID" / "NO_DATA"
    """
    clean_sym = symbol.strip().upper()
    if not clean_sym.endswith(".NS") and not clean_sym.endswith(".BO") and "^" not in clean_sym:
        clean_sym = f"{clean_sym}.NS"

    try:
        t = yf.Ticker(clean_sym)
        df = t.history(period="2d", interval="5m")
        if df.empty or "Close" not in df.columns or "Volume" not in df.columns:
            df = t.history(period="1d", interval="15m")

        if df.empty or len(df) == 0:
            return {"session_vwap": None, "latest_close": None, "status": "NO_DATA"}

        if isinstance(df.index, pd.DatetimeIndex):
            latest_date = df.index[-1].date()
            session_df = df[df.index.date == latest_date].copy()
        else:
            session_df = df.copy()

        if session_df.empty:
            session_df = df.iloc[-50:].copy()

        typical_price = (session_df["High"] + session_df["Low"] + session_df["Close"]) / 3.0
        volume = session_df["Volume"].replace(0, np.nan).fillna(0)

        cum_pv = (typical_price * volume).sum()
        cum_vol = volume.sum()

        if cum_vol > 0:
            session_vwap = float(cum_pv / cum_vol)
            latest_close = float(session_df["Close"].iloc[-1])
            diff = latest_close - session_vwap
            diff_pct = (diff / session_vwap) * 100.0 if session_vwap > 0 else 0.0

            return {
                "symbol": clean_sym,
                "session_vwap": round(session_vwap, 2),
                "latest_close": round(latest_close, 2),
                "vwap_diff": round(diff, 2),
                "vwap_diff_pct": round(diff_pct, 2),
                "bar_count": len(session_df),
                "session_date": str(latest_date) if 'latest_date' in locals() else "Current Session",
                "timeframe": "5m Intraday Session",
                "status": "VALID",
            }
    except Exception as e:
        print(f"Error computing session VWAP for {symbol}: {e}")

    return {"session_vwap": None, "latest_close": None, "status": "ERROR"}
