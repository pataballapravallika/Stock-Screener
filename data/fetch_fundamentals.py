from typing import Dict, Any, Optional
from data.providers.nse_xbrl_provider import NSEXBRLProvider
from data.providers.official_reports_provider import OfficialReportsProvider


_provider = NSEXBRLProvider()
_fallback_provider = OfficialReportsProvider()


def fetch_fundamentals(symbol: str) -> Dict[str, Any]:
    """Fetch fundamentals from official sources only.

    Priority order:
      1) NSE XBRL (official company filings) — primary
      2) screener.in (official reports) — fallback

    yfinance is NEVER used for fundamentals; only for prices.
    """
    try:
        result = _provider.build_fundamentals_dict(symbol)
        if result and result.get("Symbol"):
            return result
    except Exception as e:
        print(f"NSE XBRL error {symbol}: {e}")

    try:
        result = _fallback_provider.build_fundamentals_dict(symbol)
        if result and result.get("Symbol"):
            return result
    except Exception as e:
        print(f"Screener fallback error {symbol}: {e}")

    return {}
