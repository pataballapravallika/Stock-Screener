from typing import Dict, Any, Optional
from data.providers.nse_xbrl_provider import NSEXBRLProvider
from data.providers.official_reports_provider import OfficialReportsProvider


_provider = NSEXBRLProvider()
_fallback_provider = OfficialReportsProvider()


def _enrich_missing_fundamentals(symbol: str, result: Dict[str, Any]) -> Dict[str, Any]:
    if not result:
        result = {"Symbol": symbol}

    needs_enrichment = (
        not result.get("MarketCap") or
        not result.get("PE") or
        result.get("Promoter_Pct") is None or
        result.get("Institutional_Pct") is None
    )

    if needs_enrichment:
        try:
            import yfinance as yf
            clean_sym = symbol if symbol.endswith(".NS") or symbol.endswith(".BO") else f"{symbol}.NS"
            info = yf.Ticker(clean_sym).info or {}

            if not result.get("MarketCap") and info.get("marketCap"):
                # Convert to Cr
                result["MarketCap"] = float(info["marketCap"]) / 1e7

            if not result.get("PE") and info.get("trailingPE"):
                result["PE"] = round(float(info["trailingPE"]), 2)

            if not result.get("ROE") and info.get("returnOnEquity"):
                result["ROE"] = round(float(info["returnOnEquity"]) * 100.0, 2)

            prom = info.get("heldPercentInsiders")
            if result.get("Promoter_Pct") is None and prom is not None:
                result["Promoter_Pct"] = round(float(prom) * 100.0, 2)
                result["InsidersPercentHeld"] = result["Promoter_Pct"]

            inst = info.get("heldPercentInstitutions")
            if result.get("Institutional_Pct") is None and inst is not None:
                result["Institutional_Pct"] = round(float(inst) * 100.0, 2)
                result["InstitutionsPercentHeld"] = result["Institutional_Pct"]

            if result.get("FII_Pct") is None and result.get("Institutional_Pct") is not None:
                result["FII_Pct"] = round(result["Institutional_Pct"] * 0.6, 2)
                result["DII_Pct"] = round(result["Institutional_Pct"] * 0.4, 2)

            if not result.get("Company") and info.get("shortName"):
                result["Company"] = info.get("shortName")

            if (not result.get("Sector") or result.get("Sector") in ("Unknown", "N/A", "25")) and info.get("sector"):
                result["Sector"] = info.get("sector")

            if (not result.get("Industry") or result.get("Industry") in ("Unknown", "N/A", "25")) and info.get("industry"):
                result["Industry"] = info.get("industry")
        except Exception as e:
            print(f"Enrichment error for {symbol}: {e}")

    return result


_fundamentals_cache = {}


def fetch_fundamentals(symbol: str) -> Dict[str, Any]:
    """Fetch fundamentals from official sources, enriched with market data.

    Priority order:
      1) NSE XBRL (official company filings) — primary
      2) screener.in (official reports) — fallback
      3) yfinance info fallback for any missing MarketCap/PE/shareholding fields.
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
