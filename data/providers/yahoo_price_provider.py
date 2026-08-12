"""Yahoo Finance provider for market price and supplementary holder data.

Primary use is for current market price, OHLCV, and volume data.  The
holder-accessor methods (institutional, mutual fund, insider, major) provide
supplementary ownership context.  Fundamental financial data comes
exclusively from NSE XBRL and official sources — this provider does NOT
provide fundamentals or financial ratios.
"""
import math

import yfinance as yf
import pandas as pd
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone


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
    """Provides market price, OHLCV, and holder data via Yahoo Finance.

    Primary use is for current market price data (price, volume).  The
    institutional / mutual-fund / insider holder methods are convenience
    accessors for supplementary ownership context.  Fundamental financial
    data comes exclusively from NSE XBRL and official sources — this
    provider does NOT provide fundamentals or financial ratios.
    """

    def __init__(self):
        self.session = None

    @staticmethod
    def _resolve_ticker(symbol: str) -> str:
        clean = symbol.strip().upper()
        if clean.endswith(".NS") or clean.endswith(".BO"):
            return clean
        # Try NSE first
        return f"{clean}.NS"

    def get_company_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get current market price data via Yahoo Finance.

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

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current market price (latest close)."""
        tick = self._resolve_ticker(symbol)
        try:
            ticker = yf.Ticker(tick)
            hist = ticker.history(period="2d", interval="1m")
            if hist is not None and not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception:
            pass
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

    def get_institutional_holders(self, symbol: str) -> Optional[pd.DataFrame]:
        """Fetch institutional holder details from Yahoo Finance.

        Returns a DataFrame with columns: Holder, Shares, Date Reported,
        % Out, Value, and Type. Returns None if unavailable.
        """
        tick = self._resolve_ticker(symbol)
        try:
            ticker = yf.Ticker(tick)
            holders = ticker.institutional_holders
            if holders is None or holders.empty:
                return None
            df = holders.copy()
            df.columns = [str(c).strip() for c in df.columns]
            return df
        except Exception as e:
            print(f"Yahoo institutional holders error {symbol}: {e}")
            return None

    def get_mutual_fund_holders(self, symbol: str) -> Optional[pd.DataFrame]:
        """Fetch mutual fund holder details from Yahoo Finance.

        Returns a DataFrame with columns: Holder, Shares, Date Reported,
        % Out, Value. Returns None if unavailable.
        """
        tick = self._resolve_ticker(symbol)
        try:
            ticker = yf.Ticker(tick)
            holders = ticker.mutualfund_holders
            if holders is None or holders.empty:
                return None
            df = holders.copy()
            df.columns = [str(c).strip() for c in df.columns]
            return df
        except Exception as e:
            print(f"Yahoo mutual fund holders error {symbol}: {e}")
            return None

    def get_insider_transactions(self, symbol: str) -> Optional[pd.DataFrame]:
        """Fetch recent insider transaction history from Yahoo Finance.

        Returns a DataFrame with columns: Insider, SEC, Date, Transaction
        Cost, Shares, Value, and Shares Held. Returns None if unavailable.
        """
        tick = self._resolve_ticker(symbol)
        try:
            ticker = yf.Ticker(tick)
            txns = ticker.insider_transactions
            if txns is None or txns.empty:
                return None
            df = txns.copy()
            df.columns = [str(c).strip() for c in df.columns]
            return df
        except Exception as e:
            print(f"Yahoo insider transactions error {symbol}: {e}")
            return None

    def get_insider_purchases(self, symbol: str) -> Optional[pd.DataFrame]:
        """Fetch recent insider purchase/sale summaries from Yahoo Finance.

        Returns a DataFrame with columns: Insider, Transaction, None /
        Shares, Price, and Value. Returns None if unavailable.
        """
        tick = self._resolve_ticker(symbol)
        try:
            ticker = yf.Ticker(tick)
            purchases = ticker.insider_purchases
            if purchases is None or purchases.empty:
                return None
            df = purchases.copy()
            df.columns = [str(c).strip() for c in df.columns]
            return df
        except Exception as e:
            print(f"Yahoo insider purchases error {symbol}: {e}")
            return None

    def get_insider_roster(self, symbol: str) -> Optional[pd.DataFrame]:
        """Fetch insider roster (officers and directors) from Yahoo Finance.

        Returns a DataFrame with columns: Insider, Position, and other
        metadata. Returns None if unavailable.
        """
        tick = self._resolve_ticker(symbol)
        try:
            ticker = yf.Ticker(tick)
            roster = ticker.insider_roster_holders
            if roster is None or roster.empty:
                return None
            df = roster.copy()
            df.columns = [str(c).strip() for c in df.columns]
            return df
        except Exception as e:
            print(f"Yahoo insider roster error {symbol}: {e}")
            return None

    def get_major_holders(self, symbol: str) -> Optional[pd.DataFrame]:
        """Fetch major holders (breakdown by share type) from Yahoo Finance.

        Returns a DataFrame indexed by category. Returns None if unavailable.
        """
        tick = self._resolve_ticker(symbol)
        try:
            ticker = yf.Ticker(tick)
            holders = ticker.major_holders
            if holders is None or holders.empty:
                return None
            df = holders.copy()
            df.columns = [str(c).strip() for c in df.columns]
            return df
        except Exception as e:
            print(f"Yahoo major holders error {symbol}: {e}")
            return None
