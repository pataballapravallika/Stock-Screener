import yfinance as yf
import pandas as pd
from typing import Dict, Any, Optional

from data.providers.base_provider import BaseFundamentalProvider


class YahooPriceProvider(BaseFundamentalProvider):
    """Price-only provider.

    Uses yfinance strictly for OHLCV and historical price data.
    Does NOT provide any financial statements or ratios.
    """

    def get_company_info(self, symbol: str) -> Dict[str, Any]:
        return {}

    def get_quarterly_financials(self, symbol: str) -> Optional[pd.DataFrame]:
        return None

    def get_annual_financials(self, symbol: str) -> Optional[pd.DataFrame]:
        return None

    def get_quarterly_balance_sheet(self, symbol: str) -> Optional[pd.DataFrame]:
        return None

    def get_annual_balance_sheet(self, symbol: str) -> Optional[pd.DataFrame]:
        return None

    def get_quarterly_cashflow(self, symbol: str) -> Optional[pd.DataFrame]:
        return None

    def get_annual_cashflow(self, symbol: str) -> Optional[pd.DataFrame]:
        return None

    def get_source(self) -> str:
        return "yahoo_finance_prices"

    @staticmethod
    def fetch_prices(symbol: str, period: str = "max", interval: str = "1d") -> pd.DataFrame:
        df = yf.download(
            symbol,
            period=period,
            interval=interval,
            auto_adjust=False,
            actions=False,
            progress=False,
        )
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"])
        return df
