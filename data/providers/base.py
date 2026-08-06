from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, Any, Optional


class FundamentalProvider(ABC):
    """Abstract provider for fundamentals and corporate data."""

    @abstractmethod
    def get_info(self, symbol: str) -> Dict[str, Any]:
        """Return basic company info (dict)."""

    @abstractmethod
    def get_quarterly_financials(self, symbol: str) -> Optional[pd.DataFrame]:
        """Return quarterly financials DataFrame or None."""

    @abstractmethod
    def get_annual_financials(self, symbol: str) -> Optional[pd.DataFrame]:
        """Return annual income statement DataFrame or None."""

    @abstractmethod
    def get_balance_sheet(self, symbol: str) -> Optional[pd.DataFrame]:
        """Return annual balance sheet DataFrame or None."""

    @abstractmethod
    def get_cashflow(self, symbol: str) -> Optional[pd.DataFrame]:
        """Return annual cashflow DataFrame or None."""
