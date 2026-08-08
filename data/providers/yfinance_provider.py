import yfinance as yf
import pandas as pd
from typing import Dict, Any, Optional
from data.providers.base_provider import BaseFundamentalProvider


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


class YahooFinanceProvider(BaseFundamentalProvider):
    """Provider that wraps yfinance but returns structured results and metadata.

    This keeps a clear boundary so providers can be swapped later.
    NOTE: Use YahooPriceProvider for OHLCV-only data.
    """

    def get_company_info(self, symbol: str) -> Dict[str, Any]:
        t = yf.Ticker(symbol)
        return t.info or {}

    def get_quarterly_financials(self, symbol: str) -> Optional[pd.DataFrame]:
        t = yf.Ticker(symbol)
        df = getattr(t, "quarterly_financials", None)
        if df is None or df.empty:
            return None
        return _normalize_df(df)

    def get_quarterly_balance_sheet(self, symbol: str) -> Optional[pd.DataFrame]:
        t = yf.Ticker(symbol)
        df = getattr(t, "quarterly_balance_sheet", None)
        if df is None or df.empty:
            return None
        return _normalize_df(df)

    def get_annual_financials(self, symbol: str) -> Optional[pd.DataFrame]:
        t = yf.Ticker(symbol)
        df = getattr(t, "financials", None)
        if df is None or df.empty:
            return None
        return _normalize_df(df)

    def get_balance_sheet(self, symbol: str) -> Optional[pd.DataFrame]:
        t = yf.Ticker(symbol)
        df = getattr(t, "balance_sheet", None)
        if df is None or df.empty:
            return None
        return _normalize_df(df)

    def get_cashflow(self, symbol: str) -> Optional[pd.DataFrame]:
        t = yf.Ticker(symbol)
        df = getattr(t, "cashflow", None)
        if df is None or df.empty:
            return None
        return _normalize_df(df)

    def get_source(self) -> str:
        return "yahoo_finance"
