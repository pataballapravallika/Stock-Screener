"""Yahoo Finance provider for OHLCV market price data only.

This provider is EXCLUSIVELY for current market price, OHLCV, and volume
data.  It MUST NOT be used for any fundamental data, financial statements,
ownership ratios, or holder listings.  Fundamental data comes exclusively
from NSE XBRL official filings via NSEXBRLProvider.
"""
import math

import yfinance as yf
import pandas as pd
from typing import Dict, Any, Optional


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


class YahooPriceProvider:
    """Provides market price, OHLCV, and volume data via Yahoo Finance.

    This provider is used ONLY for:
      - Current market price (latest close)
      - Open / High / Low / Close / Volume
      - Historical price data (OHLCV bars for charting / technical analysis)

    It does NOT provide:
      - Fundamental financial data (totalDebt, totalCash, ebitda, etc.)
      - Ownership / shareholder data (institutional holders, mutual funds, etc.)
      - Earnings or revenue figures

    All fundamental data comes from NSE XBRL official filings via
    NSEXBRLProvider.  This provider must never be used as a fundamental
    data source.
    """

    def __init__(self):
        self.session = None

    @staticmethod
    def _resolve_ticker(symbol: str) -> str:
        clean = symbol.strip().upper()
        if clean.endswith(".NS") or clean.endswith(".BO"):
            return clean
        return f"{clean}.NS"

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current market price (latest close) from the OHLCV price feed."""
        tick = self._resolve_ticker(symbol)
        try:
            ticker = yf.Ticker(tick)
            hist = ticker.history(period="2d", interval="1m")
            if hist is not None and not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception:
            pass
        return None

    def get_company_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get current market price metadata via Yahoo Finance OHLCV feed.

        Returns only price-related metadata.  Fundamental financial data
        (market cap, shares outstanding, total debt, etc.) must be sourced
        from official NSE XBRL / company filings.
        """
        tick = self._resolve_ticker(symbol)
        try:
            ticker = yf.Ticker(tick)
            hist = ticker.history(period="2d", interval="1m")
            current_price = float(hist["Close"].iloc[-1]) if hist is not None and not hist.empty else None
            return {
                "current_price": current_price,
                "currency": "INR",
            }
        except Exception as e:
            print(f"Yahoo price info error {symbol}: {e}")
            return None

    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> Optional[pd.DataFrame]:
        """Get OHLCV history for charting/technical analysis."""
        tick = self._resolve_ticker(symbol)
        try:
            ticker = yf.Ticker(tick)
            hist = ticker.history(period=period, interval=interval)
            return hist
        except Exception as e:
            print(f"Yahoo history error {symbol}: {e}")
            return None

    def get_history_intraday(self, symbol: str, days: int = 1) -> Optional[pd.DataFrame]:
        """Get intraday OHLCV bars for VWAP calculation.

        Uses 5-minute intervals for the specified number of days.
        """
        tick = self._resolve_ticker(symbol)
        try:
            ticker = yf.Ticker(tick)
            period_str = f"{days}d" if days <= 7 else "1y"
            hist = ticker.history(period=period_str, interval="5m")
            return hist
        except Exception as e:
            print(f"Yahoo intraday error {symbol}: {e}")
            return None
