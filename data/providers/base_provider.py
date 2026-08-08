from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union
import pandas as pd


class BaseFundamentalProvider(ABC):
    """Abstract base for all fundamental data providers.

    All providers must implement the same contract so they can be
    swapped transparently by the data layer.
    """

    @abstractmethod
    def get_company_info(self, symbol: str) -> Dict[str, Any]:
        """Return basic company metadata."""

    @abstractmethod
    def get_quarterly_financials(self, symbol: str) -> Optional[pd.DataFrame]:
        """Return quarterly income-statement data or None."""

    @abstractmethod
    def get_annual_financials(self, symbol: str) -> Optional[pd.DataFrame]:
        """Return annual income-statement data or None."""

    @abstractmethod
    def get_quarterly_balance_sheet(self, symbol: str) -> Optional[pd.DataFrame]:
        """Return quarterly balance-sheet data or None."""

    @abstractmethod
    def get_annual_balance_sheet(self, symbol: str) -> Optional[pd.DataFrame]:
        """Return annual balance-sheet data or None."""

    @abstractmethod
    def get_quarterly_cashflow(self, symbol: str) -> Optional[pd.DataFrame]:
        """Return quarterly cash-flow data or None."""

    @abstractmethod
    def get_annual_cashflow(self, symbol: str) -> Optional[pd.DataFrame]:
        """Return annual cash-flow data or None."""

    @abstractmethod
    def get_source(self) -> str:
        """Return a human-readable identifier for this provider."""


class ReportIngestionMixin:
    """Shared helpers for providers that ingest raw report files/URLs."""

    @staticmethod
    def is_url(text: str) -> bool:
        return text.startswith("http://") or text.startswith("https://")

    @staticmethod
    def is_file(text: str) -> bool:
        import os
        return os.path.exists(text)

    @staticmethod
    def infer_format(text: str) -> Optional[str]:
        lower = text.lower()
        if lower.endswith(".pdf"):
            return "pdf"
        if lower.endswith(".xml") or lower.endswith(".xbrl"):
            return "xbrl"
        if lower.endswith(".html") or lower.endswith(".htm"):
            return "html"
        if ReportIngestionMixin.is_url(text):
            return "url"
        return None
