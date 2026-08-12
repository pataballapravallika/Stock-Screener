from typing import Dict, Any, Optional
from data.providers.nse_xbrl_provider import NSEXBRLProvider
from data.providers.official_reports_provider import OfficialReportsProvider
from data.providers.yahoo_price_provider import YahooPriceProvider


_provider = NSEXBRLProvider()
_fallback_provider = OfficialReportsProvider()
_price_provider = YahooPriceProvider()


def _enrich_missing_fundamentals(symbol: str, result: Dict[str, Any]) -> Dict[str, Any]:
    if not result:
        result = {"Symbol": symbol}

    needs_enrichment = (
        not result.get("MarketCap") or
        not result.get("PE") or
        not result.get("Company") or
        not result.get("Sector") or
        not result.get("Industry") or
        result.get("Sector") in ("Unknown", "N/A", "25") or
        result.get("Industry") in ("Unknown", "N/A", "25")
    )

    if needs_enrichment:
        try:
            from data.providers.official_reports_provider import OfficialReportsProvider
            off_info = OfficialReportsProvider().get_company_info(symbol)
            if off_info:
                if not result.get("Company"):
                    result["Company"] = off_info.get("company_name")
                if not result.get("Sector") or result.get("Sector") in ("Unknown", "N/A", "25"):
                    result["Sector"] = off_info.get("sector") or result.get("Sector")
                if not result.get("Industry") or result.get("Industry") in ("Unknown", "N/A", "25"):
                    result["Industry"] = off_info.get("industry") or result.get("Industry")
        except Exception:
            pass

    if not result.get("MarketCap"):
        try:
            from data.database import get_company_info as db_get_company_info
            cached = db_get_company_info(symbol)
            if cached and cached.get("market_cap"):
                result["MarketCap"] = float(cached["market_cap"])
        except Exception:
            pass

    if not result.get("SharesOutstanding"):
        try:
            from data.database import get_company_info as db_get_company_info
            cached = db_get_company_info(symbol)
            if cached and cached.get("shares_outstanding"):
                result["SharesOutstanding"] = cached["shares_outstanding"]
        except Exception:
            pass

    return result


_fundamentals_cache = {}


def fetch_fundamentals(symbol: str) -> Dict[str, Any]:
    """Fetch fundamentals from official sources only.

    Priority order:
      1) NSE XBRL (official company filings) — primary
      2) screener.in (official reports) — fallback
      YFinance is NOT used for fundamentals, ownership, or ratios.
      YFinance is used ONLY for current market price data (price, volume).
    """
    clean_sym = symbol.strip().upper()
    if clean_sym in _fundamentals_cache:
        return _fundamentals_cache[clean_sym]

    res = {}
    try:
        res = _provider.build_fundamentals_dict(clean_sym)
    except Exception as e:
        print(f"NSE XBRL error {clean_sym}: {e}")

    if not res or not res.get("Symbol") or not res.get("MarketCap"):
        try:
            off_res = _fallback_provider.build_fundamentals_dict(clean_sym)
            if off_res:
                for k, v in off_res.items():
                    if v is not None and not res.get(k):
                        res[k] = v
        except Exception as e:
            print(f"Screener fallback error {clean_sym}: {e}")

    enriched = _enrich_missing_fundamentals(clean_sym, res)
    _fundamentals_cache[clean_sym] = enriched
    return enriched


def clear_fundamentals_cache():
    """Clear the fundamentals cache so fresh data is fetched on next call."""
    global _fundamentals_cache
    _fundamentals_cache = {}
