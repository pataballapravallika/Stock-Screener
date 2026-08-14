from typing import Dict, Any, Optional
from data.providers.nse_xbrl_provider import NSEXBRLProvider


_provider = NSEXBRLProvider()


def _is_truthy(val: Any) -> bool:
    """Safe truthiness check that handles pandas DataFrames/Series."""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    if hasattr(val, "empty"):
        return not val.empty
    return bool(val)


_fundamentals_cache: Dict[str, Dict[str, Any]] = {}


def fetch_fundamentals(symbol: str) -> Dict[str, Any]:
    """Fetch fundamentals from the official NSE XBRL filing data source only.

    Primary source: NSE Integrated Filing XBRL documents (nseindia.com).

    Yahoo Finance is used ONLY for current market price (OHLCV) in
    fetch_prices / pages — never for fundamentals, ownership, or ratios.

    If a value cannot be reliably extracted from the official NSE filing,
    it is returned as N/A.  No third-party (Yahoo Finance, Trendlyne,
    MarketSmith, Screener.in, etc.) fundamental data is ever used.
    """
    clean_sym = symbol.strip().upper()
    if clean_sym in _fundamentals_cache:
        return _fundamentals_cache[clean_sym]

    res = {}
    try:
        res = _provider.build_fundamentals_dict(clean_sym)
    except Exception as e:
        print(f"NSE XBRL error {clean_sym}: {e}")
        res = {"Symbol": clean_sym}

    if not res or not res.get("Symbol"):
        res = {"Symbol": clean_sym}

    _fundamentals_cache[clean_sym] = res
    return res


def clear_fundamentals_cache():
    """Clear the fundamentals cache so fresh data is fetched on next call."""
    global _fundamentals_cache
    _fundamentals_cache = {}
