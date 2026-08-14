"""NSE XBRL provider — fetches official corporate financial filings from NSE India.

Primary source of truth for fundamental data.
Downloads "Integrated Filing - Financials" XBRL documents from nseindia.com
and extracts reported quarterly and annual values via the ``nse-xbrl`` library
(or a built-in HTTP fallback when the package is not installed).

Every stored metric carries:
  - company
  - ticker
  - period          ("quarterly" / "annual")
  - quarter / financial_year
  - report_date     (period end date)
  - consolidated    (bool)
  - value / unit
  - source URL      (XBRL file URL)
  - source_type     ("nse_xbrl")
"""

import math
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import requests

from data.providers.base_provider import BaseFundamentalProvider, ReportIngestionMixin
from data.parsers.xbrl_parser import XBRLParser
from data.calculations.financial_calculator import FinancialCalculator
from fundamentals.banking import compute_banking_metrics
from data.database import (
    init_db,
    save_company_info,
    get_company_info,
    save_fundamental_report,
    get_latest_quarterly_reports,
    get_latest_annual_reports,
    save_ttm_record,
    get_ttm_record,
    purge_non_nse_reports,
)


class _ReportHelpers:
    """Self-contained reporting period helpers (no third-party dependencies)."""

    @staticmethod
    def normalize_period(period_str: str) -> Optional[str]:
        if period_str is None:
            return None
        s = str(period_str).strip()
        if not s:
            return None
        try:
            dt = pd.to_datetime(s)
            end_dt = dt + pd.offsets.MonthEnd(0)
            return end_dt.strftime("%Y-%m-%d")
        except Exception:
            return s

    @staticmethod
    def derive_quarter(period_str: str) -> Optional[int]:
        s = _ReportHelpers.normalize_period(period_str)
        if s is None:
            return None
        try:
            dt = pd.to_datetime(s)
            month = dt.month
            if 4 <= month <= 6:
                return 1
            elif 7 <= month <= 9:
                return 2
            elif 10 <= month <= 12:
                return 3
            else:
                return 4
        except Exception:
            return None

    @staticmethod
    def derive_financial_year(period_str: str, quarter: Optional[int] = None) -> Optional[int]:
        s = str(period_str).strip() if period_str else ""
        if not s:
            return None
        m = re.match(r'^[Ff][Yy]\s*(\d{2,4})$', s)
        if m:
            yr = int(m.group(1))
            if yr < 100:
                yr += 2000
            return yr
        try:
            dt = pd.to_datetime(s)
            month = dt.month
            if month >= 4:
                return dt.year + 1
            else:
                return dt.year
        except Exception:
            return None

    @staticmethod
    def derive_annual_financial_year(period_str: str) -> Optional[int]:
        s = str(period_str).strip() if period_str else ""
        if not s:
            return None
        m = re.match(r'^[Ff][Yy]\s*(\d{2,4})$', s)
        if m:
            yr = int(m.group(1))
            if yr < 100:
                yr += 2000
            return yr
        m2 = re.match(r'^[A-Za-z]{3,}\s+(\d{4})$', s)
        if m2:
            return int(m2.group(1))
        try:
            yr = int(s.strip())
            if yr < 100:
                yr += 2000
            return yr
        except (ValueError, TypeError):
            return None


class NSEXBRLProvider(BaseFundamentalProvider, ReportIngestionMixin):
    """Provider that fetches official NSE Integrated Filing XBRL data.

    Uses the ``nse-xbrl`` package when available (preferred), otherwise
    falls back to a built-in HTTP fetcher that hits the same NSE JSON
    endpoints + a stdlib XML parser.

    Never uses yfinance for fundamentals.
    """

    NSE_BASE = "https://www.nseindia.com"
    NSE_API = "/api"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Referer": "https://www.nseindia.com/",
    }

    def __init__(self):
        init_db()
        self.calculator = FinancialCalculator()
        self._session = None
        self._issuer_map = {}
        self._nse_purged = False

    def _get_session(self):
        if self._session is None:
            s = requests.Session()
            s.headers.update(self.HEADERS)
            try:
                s.get(self.NSE_BASE, timeout=15)
            except Exception:
                pass
            self._session = s
        return self._session

    def _nse_get(self, endpoint: str, params: Optional[dict] = None, referer_path: str = "/"):
        session = self._get_session()
        url = f"{self.NSE_BASE}{endpoint}" if endpoint.startswith("/") else endpoint
        headers = dict(self.HEADERS)
        if referer_path:
            headers["Referer"] = f"{self.NSE_BASE}{referer_path}"

        for attempt in range(2):
            try:
                resp = session.get(url, params=params, headers=headers, timeout=10)
                if resp.status_code in (401, 403):
                    # NSE actively blocking — session needs a new cookie
                    session.get(self.NSE_BASE, timeout=10)
                    continue
                if resp.status_code == 500:
                    session.get(self.NSE_BASE, timeout=10)
                    continue
                resp.raise_for_status()
                return resp.json()
            except Exception:
                if attempt < 1:
                    time.sleep(0.5)
        return None

    def _nse_get_html(self, path: str, params: Optional[dict] = None) -> Optional[str]:
        session = self._get_session()
        url = f"{self.NSE_BASE}{path}" if path.startswith("/") else path
        try:
            resp = session.get(url, params=params, timeout=25)
            resp.raise_for_status()
            return resp.text
        except Exception:
            return None

    def get_company_info(self, symbol: str) -> Dict[str, Any]:
        cached = get_company_info(symbol)
        if cached and cached.get("company_name") and cached.get("sector") and cached.get("sector") != "Unknown":
            result = {
                "ticker": symbol,
                "company_name": cached.get("company_name"),
                "sector": cached.get("sector"),
                "industry": cached.get("industry"),
                "market_cap": cached.get("market_cap"),
                "sharesOutstanding": cached.get("shares_outstanding"),
                # Return cached shareholding data if available
                "Promoter_Pct": cached.get("promoter_pct"),
                "FII_Pct": cached.get("fii_pct"),
                "DII_Pct": cached.get("dii_pct"),
                "Govt_Pct": cached.get("govt_pct"),
                "Public_Pct": cached.get("public_pct"),
                "Institutional_Pct": cached.get("institutional_pct"),
                "Shareholders_Count": cached.get("shareholders_count"),
                "Shareholding_Period": cached.get("shareholding_period"),
                "Shareholding_Table": None,
                "Shareholding_History": None,
            }

            sh_json = cached.get("shareholding_json")
            if sh_json:
                try:
                    import json as _json
                    table_df = pd.DataFrame(_json.loads(sh_json))
                    result["Shareholding_Table"] = table_df
                    if not table_df.empty and table_df.shape[1] >= 2:
                        result["Shareholding_History"] = self._build_history_from_table(table_df)
                except Exception:
                    pass

            return result

        clean = self._ticker_to_slug(symbol)
        data = self._nse_get(f"/api/quote-equity?symbol={clean}")

        company_name = clean
        sector = None
        industry = None
        mcap = None
        shares = None

        if data and isinstance(data, dict):
            info_rec = data.get("info", {})
            sec_info = data.get("industryInfo", {})
            price_info = data.get("priceInfo", {})
            sec_details = data.get("secInfo", {})

            company_name = info_rec.get("companyName") or clean
            sector = sec_info.get("macro") or sec_info.get("sector")
            industry = sec_info.get("industry") or sec_info.get("basicIndustry")

            if "marketCap" in sec_details:
                mcap = self._to_float(sec_details.get("marketCap"))
            elif "totalMarketCap" in price_info:
                mcap = self._to_float(price_info.get("totalMarketCap"))

            shares = self._to_float(sec_details.get("issuedCap"))

        # If NSE quote API failed (e.g., 403 blocked), fall back to DB cache
        # for market_cap and shares metadata.  These are quote-level metadata
        # from the NSE quote API, not fundamental line items from filings.
        if not mcap or not shares:
            try:
                cached = get_company_info(symbol)
                if cached:
                    mcap = mcap or cached.get("market_cap")
                    shares = shares or cached.get("shares_outstanding")
                    company_name = company_name or cached.get("company_name")
                    sector = sector or cached.get("sector")
                    industry = industry or cached.get("industry")
            except Exception:
                pass

        # Last resort: derive shares from XBRL filing data (Equity Share Capital / Face Value)
        # This is the only acceptable fallback for shares — it comes from official NSE XBRL filings.
        if not shares:
            try:
                a_df = get_latest_annual_reports(symbol, limit=1)
                if not a_df.empty:
                    share_cap = a_df.iloc[0].get("share_capital")
                    face_val = a_df.iloc[0].get("face_value")
                    if share_cap is not None and face_val is not None and face_val > 0:
                        shares = (float(share_cap) * 1e7) / float(face_val)
            except Exception:
                pass

        if not sector or sector == "Unknown":
            sector = "N/A"
        if not industry or industry == "Unknown":
            industry = "N/A"

        sector = sector or "N/A"
        industry = industry or "N/A"

        result = {
            "ticker": symbol,
            "company_name": company_name,
            "sector": sector,
            "industry": industry,
            "market_cap": mcap,
            "sharesOutstanding": shares,
        }

        save_company_info(
            symbol=symbol,
            company_name=company_name,
            sector=sector,
            industry=industry,
            market_cap=mcap,
            shares_outstanding=shares,
        )

        return result

    @staticmethod
    def _ticker_to_slug(symbol: str) -> str:
        return symbol.split(".")[0].upper()

    def _resolve_issuer(self, symbol: str) -> Optional[str]:
        clean = self._ticker_to_slug(symbol)
        if clean in self._issuer_map:
            return self._issuer_map[clean]

        data = self._nse_get(f"/api/quote-equity?symbol={clean}")
        if data and isinstance(data, dict):
            info = data.get("info", {})
            company_name = info.get("companyName")
            if company_name:
                self._issuer_map[clean] = company_name
                return company_name

        self._issuer_map[clean] = clean
        return clean

    def get_shareholding(self, symbol: str) -> Dict[str, Any]:
        """Fetch official shareholding pattern from NSE's shareholder disclosures.

        Source is the NSE shareholder-patterns API endpoint
        (/api/shareholder-patterns).  If it returns 404/403, no fallback
        is used — values remain None so N/A is displayed in the UI.

        Returns a dict with:
            - Promoter_Pct
            - FII_Pct
            - DII_Pct
            - Govt_Pct
            - Public_Pct
            - Institutional_Pct
            - Shareholders_Count
            - Shareholding_Period
            - Shareholding_Table (DataFrame of the full quarterly trend)
            - Shareholding_History (dict of per-category time-series)
        All values are None if the data cannot be obtained.
        """
        clean = self._ticker_to_slug(symbol)
        sh_dict: Dict[str, Any] = {
            "Promoter_Pct": None,
            "FII_Pct": None,
            "DII_Pct": None,
            "Govt_Pct": None,
            "Public_Pct": None,
            "Institutional_Pct": None,
            "Shareholders_Count": None,
            "Shareholding_Period": None,
            "Shareholding_Table": None,
            "Shareholding_History": None,
        }

        # Check database cache first to avoid redundant network calls
        cached = get_company_info(symbol)
        if cached and cached.get("company_name"):
            cached_pct_total = (cached.get("promoter_pct") or 0) + (cached.get("fii_pct") or 0) + (cached.get("dii_pct") or 0)
            if cached_pct_total > 0:
                sh_dict.update({
                    "Promoter_Pct": cached.get("promoter_pct"),
                    "FII_Pct": cached.get("fii_pct"),
                    "DII_Pct": cached.get("dii_pct"),
                    "Govt_Pct": cached.get("govt_pct"),
                    "Public_Pct": cached.get("public_pct"),
                    "Shareholders_Count": cached.get("shareholders_count"),
                    "Shareholding_Period": cached.get("shareholding_period"),
                })
                fii = sh_dict["FII_Pct"]
                dii = sh_dict["DII_Pct"]
                if fii is not None and dii is not None:
                    sh_dict["Institutional_Pct"] = round(fii + dii, 2)
                elif fii is not None:
                    sh_dict["Institutional_Pct"] = fii
                elif dii is not None:
                    sh_dict["Institutional_Pct"] = dii

                # Reconstruct Shareholding_Table and Shareholding_History from JSON if available
                sh_json = cached.get("shareholding_json")
                if sh_json:
                    try:
                        import json as _json
                        table_df = pd.DataFrame(_json.loads(sh_json))
                        sh_dict["Shareholding_Table"] = table_df
                        sh_dict["Shareholding_History"] = self._build_history_from_table(table_df)
                    except Exception:
                        pass

                return sh_dict

        # Official NSE shareholder-patterns API for shareholding data
        endpoint = f"/api/shareholder-patterns?symbol={clean}"
        data = self._nse_get(endpoint, referer_path=f"/report-widgets/shareholder-patterns?symbol={clean}")

        if data and isinstance(data, dict):
            try:
                sh_dict = self._parse_nse_shareholding(data, sh_dict)
            except Exception:
                pass

        # Shareholding data comes ONLY from official NSE shareholder-patterns API.
        # No third-party (screener.in) fallbacks are used for ownership data.

        # Compute Institutional_Pct = FII + DII only if both are present
        fii = sh_dict["FII_Pct"]
        dii = sh_dict["DII_Pct"]
        if fii is not None and dii is not None:
            sh_dict["Institutional_Pct"] = round(fii + dii, 2)
        elif fii is not None:
            sh_dict["Institutional_Pct"] = fii
        elif dii is not None:
            sh_dict["Institutional_Pct"] = dii

        # Persist shareholding data to database for caching
        if any(sh_dict.get(k) is not None for k in ("Promoter_Pct", "FII_Pct", "DII_Pct",
                                                     "Govt_Pct", "Public_Pct", "Institutional_Pct")):
            try:
                sh_json = None
                if sh_dict.get("Shareholding_Table") is not None:
                    import json as _json
                    sh_json = _json.dumps(sh_dict["Shareholding_Table"].to_dict(orient="list"), default=str)
                save_company_info(
                    ticker=symbol,
                    promoter_pct=sh_dict.get("Promoter_Pct"),
                    fii_pct=sh_dict.get("FII_Pct"),
                    dii_pct=sh_dict.get("DII_Pct"),
                    govt_pct=sh_dict.get("Govt_Pct"),
                    public_pct=sh_dict.get("Public_Pct"),
                    institutional_pct=sh_dict.get("Institutional_Pct"),
                    shareholders_count=sh_dict.get("Shareholders_Count"),
                    shareholding_json=sh_json,
                    shareholding_period=sh_dict.get("Shareholding_Period"),
                )
            except Exception:
                pass

        return sh_dict

    def _parse_screener_shareholding(self, html: str, sh_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Parse shareholding pattern from screener.in HTML — DISABLED.

        Shareholding data is sourced exclusively from official NSE
        shareholder-pattern filings.  This method is retained only for
        backward compatibility but returns the unchanged sh_dict.
        """
        return sh_dict

    def _build_history_from_table(self, table: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Reconstruct Shareholding_History from a stored Shareholding_Table DataFrame."""
        if table is None or table.empty or table.shape[1] < 2:
            return None

        periods = [str(c) for c in table.columns[1:]]
        history = {"periods": periods}
        category_map = {
            "Promoters": "Promoter_Pct",
            "FIIs": "FII_Pct",
            "DIIs": "DII_Pct",
            "Government": "Govt_Pct",
            "Public": "Public_Pct",
        }

        for _, row in table.iterrows():
            label_clean = re.sub(r'[^a-zA-Z]', '', str(row.iloc[0])).lower()
            for display_name in category_map:
                if display_name.lower() in label_clean:
                    vals = []
                    for col in table.columns[1:]:
                        v_str = str(row[col]).replace("%", "").strip()
                        try:
                            vals.append(float(v_str))
                        except (ValueError, TypeError):
                            vals.append(None)
                    history[display_name] = vals
                    break

        return history

    def _parse_shareholding_table(self, table: pd.DataFrame, sh_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a screener.in shareholding table into shareholding dict."""
        n_cols = len(table.columns)
        if n_cols < 2:
            return sh_dict

        latest_col = table.columns[-1]

        label_map = {
            "Promoter_Pct": ["promoter", "promoters"],
            "FII_Pct": ["fii", "fiis", "foreigninstitutional"],
            "DII_Pct": ["dii", "diis", "domesticinstitutional"],
            "Govt_Pct": ["government", "govt"],
            "Public_Pct": ["public", "others", "publicandothers"],
        }

        for idx, row in table.iterrows():
            label_raw = str(row.iloc[0]).lower().strip()
            latest_raw = str(latest_col) if isinstance(latest_col, str) else ""

            for target_key, keywords in label_map.items():
                if sh_dict.get(target_key) is not None:
                    continue
                if any(kw in label_raw for kw in keywords):
                    val_str = str(row.iloc[-1]).replace("%", "").strip()
                    try:
                        val = float(val_str)
                        if 0 < val < 100:
                            sh_dict[target_key] = val
                            sh_dict["Shareholding_Period"] = latest_raw or str(row.iloc[-2]) if n_cols > 2 else None
                    except (ValueError, TypeError):
                        pass

        return sh_dict

    def _parse_nse_shareholding(self, data: Dict[str, Any], sh_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Parse NSE shareholder-patterns API response into shareholding dict."""
        import json as _json

        # The NSE API returns a nested structure with a list of shareholder categories
        # and their percentages for each reporting quarter
        raw = None
        if "body" in data and isinstance(data["body"], str):
            try:
                raw = _json.loads(data["body"])
            except Exception:
                pass
        elif "data" in data:
            raw = data["data"]
        else:
            raw = data

        if not raw:
            return sh_dict

        # NSE API structure: data holds a list, each with category and percentage
        records = raw if isinstance(raw, list) else [raw]

        # Look for the most recent quarter's patterns
        latest_date = None
        latest_records = None

        for rec in records:
            if isinstance(rec, dict):
                if "quarter" in rec or "date" in rec or "reportingQuarter" in rec:
                    if latest_records is None:
                        latest_date = rec.get("quarter") or rec.get("date") or rec.get("reportingQuarter")
                        latest_records = rec
                        if "patterns" in rec and isinstance(rec["patterns"], list):
                            latest_records = rec["patterns"]
                    else:
                        current_date = rec.get("quarter") or rec.get("date") or rec.get("reportingQuarter")
                        if current_date and latest_date and current_date > latest_date:
                            latest_date = current_date
                            latest_records = rec.get("patterns", rec) if isinstance(rec, dict) else rec

        if latest_records is None:
            latest_records = records

        if isinstance(latest_records, dict):
            latest_records = [latest_records]

        if not isinstance(latest_records, list):
            return sh_dict

        # Map NSE shareholder category names to our keys
        nse_category_map = {
            "promoter": "Promoter_Pct",
            "promotergroup": "Promoter_Pct",
            "foreigninstitutionalinvestorsfiimapfolder": "FII_Pct",
            "fiimapfolder": "FII_Pct",
            "fii": "FII_Pct",
            "domesticinstitutionalinvestorsdiimapfolder": "DII_Pct",
            "diimapfolder": "DII_Pct",
            "dii": "DII_Pct",
            "government": "Govt_Pct",
            "public": "Public_Pct",
            "publicandothers": "Public_Pct",
            "others": "Public_Pct",
        }

        for rec in latest_records:
            if not isinstance(rec, dict):
                continue
            # NSE pattern entries have fields like: "name"/"holder", "pctHeld"/"percentage"
            name = rec.get("name") or rec.get("holder") or rec.get("category") or ""
            pct = rec.get("pctHeld") or rec.get("percentage") or rec.get("holdingPct") or rec.get("pct")

            if pct is not None:
                pct_f = self._to_float(pct)
                if pct_f is not None:
                    name_lower = str(name).lower().strip()
                    matched = False
                    for key, mapped_key in nse_category_map.items():
                        if key in name_lower:
                            sh_dict[mapped_key] = round(pct_f, 2)
                            matched = True
                            break
                    if not matched:
                        # Try partial name matching
                        if "promot" in name_lower:
                            sh_dict["Promoter_Pct"] = round(pct_f, 2)
                        elif "fii" in name_lower or "foreigninst" in name_lower:
                            sh_dict["FII_Pct"] = round(pct_f, 2)
                        elif "dii" in name_lower or "domesticinst" in name_lower:
                            sh_dict["DII_Pct"] = round(pct_f, 2)
                        elif "govern" in name_lower:
                            sh_dict["Govt_Pct"] = round(pct_f, 2)
                        elif "public" in name_lower or "other" in name_lower:
                            sh_dict["Public_Pct"] = round(pct_f, 2)

        return sh_dict

    def ingest_from_nse(self, symbol: str, max_filings: int = 5) -> int:
        issuer = self._resolve_issuer(symbol)
        if not issuer:
            return 0

        filings = self._fetch_filings(symbol, issuer, max_filings)
        if not filings:
            return 0

        stored = 0
        for filing in filings:
            if self._store_filing(symbol, filing):
                stored += 1

        self._refresh_ttm(symbol)
        return stored

    def _fetch_filings(self, symbol: str, issuer: str, max_filings: int = 5) -> List[Any]:
        filings = self._fetch_filings_nsexbrl(symbol, issuer, max_filings)
        if filings:
            return filings
        return self._fetch_filings_builtin(symbol, issuer, max_filings)

    def _fetch_filings_nsexbrl(self, symbol: str, issuer: str, max_filings: int = 5) -> List[Any]:
        try:
            from nse_xbrl import NSEClient
            session = self._get_session()
            cookie_str = "; ".join([f"{k}={v}" for k, v in session.cookies.items()])
            if not cookie_str:
                return []
            client = NSEClient(cookie_string=cookie_str)
            filings = client.fetch_financials(symbol, issuer, max_filings=max_filings)
            enriched = []
            for f in filings:
                self._enrich_filing(f, symbol)
                enriched.append(f)
            return enriched
        except Exception:
            return []

    def _fetch_filings_builtin(self, symbol: str, issuer: str, max_filings: int = 5) -> List[dict]:
        clean = self._ticker_to_slug(symbol)
        url = f"/api/corporate-announcements?index=equities&symbol={clean}&subCategory=financial-results"
        data = self._nse_get(url)
        if not data or not isinstance(data, list):
            return []

        # NSE corporate announcement items include an attchmntFile URL for
        # the PDF attachment and, when hasXbrl is True, a companion XBRL XML.
        xbrl_url_candidates = [
            "https://nsearchives.nseindia.com/corporate/XBRL/{sym}_{dt}.xml",
            "https://nsearchives.nseindia.com/corporate/XBRL/{sym}_{dt}.XML",
            "https://nsearchives.nseindia.com/corporate/XBRL/{pdf_name}.xml",
            "https://nsearchives.nseindia.com/corporate/XBRL/{pdf_name}.XML",
            "https://nsearchives.nseindia.com/corporate/{pdf_name}.xml",
            "https://nsearchives.nseindia.com/corporate/{pdf_name}.XML",
        ]

        filings = []
        for item in data:
            if not isinstance(item, dict):
                continue
            text = str(item.get("attchmntText", "")).lower()
            has_xbrl = item.get("hasXbrl") is True
            is_financial = "financial results" in text or "outcome of board meeting" in text
            is_noise = any(w in text for w in ["transcript", "audio", "media", "presentation", "analyst", "postal"])

            if (has_xbrl or is_financial) and not is_noise:
                dt = item.get("dt", "")
                pdf_url = item.get("attchmntFile", "")
                pdf_name = pdf_url.split("/")[-1] if pdf_url else ""
                # Remove .pdf extension to build XML name
                xml_name = pdf_name.replace(".pdf", "") if pdf_name.lower().endswith(".pdf") else pdf_name

                filing_dict = {
                    "symbol": clean,
                    "company_name": item.get("symbol", clean),
                    "period_end": dt,
                    "attchmntText": item.get("attchmntText"),
                    "hasXbrl": has_xbrl,
                    "is_consolidated": "consolidated" in text or "consol" in text,
                }

                # Try each XBRL URL candidate
                parsed = None
                used_url = None
                for tmpl in xbrl_url_candidates:
                    candidate_url = tmpl.format(sym=clean, dt=dt, pdf_name=xml_name)
                    xml_text = self._fetch_url_text(candidate_url)
                    if xml_text:
                        parsed = self._parse_xbrl_stdlib(xml_text, symbol, candidate_url)
                        if parsed:
                            used_url = candidate_url
                            break

                if parsed and used_url:
                    filing_dict["xbrl_url"] = used_url
                    filing_dict.update(parsed)
                    filings.append(filing_dict)

                if len(filings) >= max_filings:
                    break
        return filings

    def _enrich_filing(self, filing: Any, symbol: str):
        url = getattr(filing, "xbrl_url", None) or getattr(filing, "xbrl_attachment", None)
        if url and isinstance(url, str):
            xml_text = self._fetch_url_text(url)
            if xml_text:
                parsed = self._parse_xbrl_stdlib(xml_text, symbol, url)
                for k, v in parsed.items():
                    if not hasattr(filing, k) or getattr(filing, k) is None:
                        setattr(filing, k, v)

    def _fetch_url_text(self, url: str) -> Optional[str]:
        session = self._get_session()
        try:
            resp = session.get(url, headers=self.HEADERS, timeout=20)
            if resp.status_code == 200:
                return resp.text
        except Exception:
            pass
        return None

    @staticmethod
    def _to_float(val: Any) -> Optional[float]:
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).strip().replace(",", "")
        if not s or s.lower() in ("n/a", "none", "nan", "nil", "-"):
            return None
        try:
            return float(s)
        except ValueError:
            return None

    @staticmethod
    def _to_crores(val: Optional[float], is_eps: bool = False) -> Optional[float]:
        """Convert raw rupee values to INR crores (divide by 10^7).

        EPS is not converted (it is already per-share in rupees).
        NSE XBRL reports monetary amounts in the entity's functional
        currency (INR) as absolute rupee values, so we divide by
        1,00,00,000 to express in crores.
        """
        if val is None:
            return None
        if is_eps:
            return val
        return val / 10000000.0

    def _parse_xbrl_stdlib(self, xml_text: str, symbol: str, xbrl_url: str) -> Dict[str, Any]:
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_text)
        except Exception:
            return {}

        data_map = {}
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            val = elem.text.strip() if elem.text else ""
            if val:
                data_map[tag.lower()] = val

        def _get(key_list: List[str]) -> Optional[float]:
            """Extract a raw value (in rupees) from the XBRL data map.

            Does NOT convert to crores — the caller (_store_filing) handles
            unit normalization so conversion happens exactly once.
            """
            for k in key_list:
                for map_k, map_v in data_map.items():
                    if k.lower() in map_k.lower():
                        flt = self._to_float(map_v)
                        if flt is not None:
                            return flt
            return None

        revenue = _get(["RevenueFromOperations", "IncomeFromOperations", "TotalRevenue", "Income", "Revenue"])
        pat = _get(["ProfitLossForPeriod", "ProfitAfterTax", "NetProfit", "ProfitLossFromOrdinaryActivitiesAfterTax"])
        eps = _get(["DilutedEarningsLossPerShare", "BasicEarningsLossPerShare", "DilutedEPS", "BasicEPS", "EPS"])
        ebit = _get(["ProfitBeforeTax", "ProfitLossBeforeTax", "EBIT"])
        total_assets = _get(["TotalAssets", "Assets"])
        equity = _get(["TotalEquity", "Equity", "PaidUpEquityShareCapital", "ShareCapital"])
        total_liab = _get(["TotalLiabilities", "Liabilities"])
        curr_assets = _get(["TotalCurrentAssets", "CurrentAssets"])
        curr_liab = _get(["TotalCurrentLiabilities", "CurrentLiabilities"])
        capex = _get(["PurchaseOfPropertyPlantAndEquipment", "CapEx", "CapitalExpenditure"])
        ocf = _get(["NetCashFlowsFromUsedInOperatingActivities", "OperatingCashFlow", "CashFlowFromOperatingActivities"])
        gross_profit = _get(["GrossProfit", "GrossProfitLossFromOperations"])
        retained_earnings = _get(["RetainedEarnings"])

        # Cash & cash equivalents
        cash_ce = _get(["CashAndCashEquivalents", "cashendcashequivalents", "cashequivalents"])

        # Total debt: sum of borrowings (current + non-current) + loans (current + non-current)
        borrowings_current = _get(["BorrowingsCurrent", "borrowingscurrent"])
        borrowings_noncurrent = _get(["BorrowingsNoncurrent", "borrowingsnoncurrent"])
        loans_current = _get(["LoansCurrent", "loanscurrent"])
        loans_noncurrent = _get(["LoansNoncurrent", "loansnoncurrent"])
        total_debt = None
        debt_components = [borrowings_current, borrowings_noncurrent, loans_current, loans_noncurrent]
        valid_debt_components = [d for d in debt_components if d is not None]
        if valid_debt_components:
            total_debt = sum(valid_debt_components)

        # Depreciation, depletion & amortisation expense
        dda = _get(["DepreciationDepletionAndAmortisationExpense", "depreciationdepletionandamortisationexpense",
                     "DepreciationAndAmortization", "depreciationamortization"])

        # Shares outstanding: equity share capital / face value per share
        share_capital = _get(["EquityShareCapital", "equitysharecapital"])
        face_value = _get(["FaceValueOfEquityShareCapital", "facevalueofequitysharecapital"])
        shares_out = None
        if share_capital is not None and face_value is not None and face_value > 0:
            # share_capital is in raw rupees, face_value is per share in rupees
            # shares_out = share_capital (rupees) / face_value (rupees/share)
            shares_out = share_capital / face_value

        # Banking-specific XBRL fields
        interest_income = _get(["InterestIncomeFromBankingActivities", "InterestIncome"])
        interest_expense = _get(["InterestExpense", "InterestPaid", "InterestCharges"])
        total_income = _get(["TotalIncome", "TotalRevenueFromOperations", "OperatingIncome"])
        non_interest_income = _get(["NonInterestIncome", "FeeAndCommissionIncome", "OtherIncome"])
        gross_npa = _get(["GrossNPA", "GrossNonPerformingAssets", "NonPerformingAssetsGross"])
        net_npa = _get(["NetNPA", "NetNonPerformingAssets", "NonPerformingAssetsNet"])
        total_advances = _get(["TotalAdvances", "TotalCredit", "GrossAdvances"])
        provisions = _get(["Provisions", "TotalProvisions", "ProvisionForNPA"])
        total_deposits = _get(["TotalDeposits", "Deposits"])
        car = _get(["CapitalAdequacyRatio", "CAR"])

        is_consol = any("consolidated" in str(k) or "consol" in str(k) for k in data_map.keys())

        result_map = {
            "q_revenue": revenue,
            "q_pat": pat,
            "q_diluted_eps": eps,
            "q_ebit": ebit,
            "bs_total_assets": total_assets,
            "bs_equity": equity,
            "bs_total_liabilities": total_liab,
            "bs_current_assets": curr_assets,
            "bs_current_liabilities": curr_liab,
            "cf_capex": capex,
            "cf_operating_cash_flow": ocf,
            "is_consolidated": is_consol,
            "xbrl_url": xbrl_url,
            "gross_profit": gross_profit,
            "retained_earnings": retained_earnings,
            "interest_income": interest_income,
            "interest_expense": interest_expense,
            "total_income": total_income,
            "non_interest_income": non_interest_income,
            "gross_npa": gross_npa,
            "net_npa": net_npa,
            "total_advances": total_advances,
            "provisions": provisions,
            "total_deposits": total_deposits,
            "car": car,
            "cash_and_cash_equivalents": cash_ce,
            "total_debt": total_debt,
            "borrowings_current": borrowings_current,
            "borrowings_noncurrent": borrowings_noncurrent,
            "loans_current": loans_current,
            "loans_noncurrent": loans_noncurrent,
            "depreciation_amortization": dda,
            "share_capital": share_capital,
            "face_value": face_value,
            "shares_outstanding": shares_out,
        }

        return result_map

    def _store_filing(self, symbol: str, filing: Any) -> bool:
        def _get_attr(attr_name, default=None):
            if hasattr(filing, attr_name):
                return getattr(filing, attr_name)
            if isinstance(filing, dict):
                return filing.get(attr_name, default)
            return default

        rev = self._to_crores(_get_attr("q_revenue") or _get_attr("ytd_revenue"))
        pat = self._to_crores(_get_attr("q_pat") or _get_attr("ytd_pat"))
        eps = _get_attr("q_diluted_eps") or _get_attr("ytd_diluted_eps")
        ebit = self._to_crores(_get_attr("q_ebit") or _get_attr("ytd_ebit"))
        gross_profit = self._to_crores(_get_attr("gross_profit"))

        assets = self._to_crores(_get_attr("bs_total_assets"))
        equity = self._to_crores(_get_attr("bs_equity"))
        liab = self._to_crores(_get_attr("bs_total_liabilities"))
        c_assets = self._to_crores(_get_attr("bs_current_assets"))
        c_liab = self._to_crores(_get_attr("bs_current_liabilities"))

        capex = self._to_crores(_get_attr("cf_capex"))
        ocf = self._to_crores(_get_attr("cf_operating_cash_flow"))

        # Use actual borrowings from XBRL if available; fall back to liab - equity
        actual_debt = self._to_crores(_get_attr("total_debt"))
        debt_val = actual_debt if actual_debt else ((liab - equity) if liab and equity else None)

        # Cash & cash equivalents from XBRL
        cash_ce = self._to_crores(_get_attr("cash_and_cash_equivalents"))

        # Depreciation & amortisation
        dda = self._to_crores(_get_attr("depreciation_amortization"))

        # Share capital and face value
        share_cap = self._to_crores(_get_attr("share_capital"))
        fv = _get_attr("face_value")
        shares_out = _get_attr("shares_outstanding")

        interest_income = self._to_crores(_get_attr("interest_income"))
        interest_expense = self._to_crores(_get_attr("interest_expense"))
        total_income = self._to_crores(_get_attr("total_income"))
        non_interest_income = self._to_crores(_get_attr("non_interest_income"))
        gross_npa = self._to_crores(_get_attr("gross_npa"))
        net_npa = self._to_crores(_get_attr("net_npa"))
        total_advances = self._to_crores(_get_attr("total_advances"))
        provisions = self._to_crores(_get_attr("provisions"))
        total_deposits = self._to_crores(_get_attr("total_deposits"))
        car = _get_attr("car")

        date_str = _get_attr("period_end") or _get_attr("dt") or ""
        report_date = _ReportHelpers.normalize_period(date_str) or datetime.now().strftime("%Y-%m-%d")

        period = _get_attr("period") or "quarterly"
        quarter = _ReportHelpers.derive_quarter(report_date)
        fy = _ReportHelpers.derive_financial_year(report_date, quarter)

        save_fundamental_report(
            ticker=symbol,
            company=symbol,
            report_date=report_date,
            period=period,
            quarter=quarter,
            financial_year=fy,
            revenue=rev,
            operating_profit=ebit,
            ebit=ebit,
            pat=pat,
            eps=eps,
            equity=equity,
            assets=assets,
            liabilities=liab,
            current_assets=c_assets,
            current_liabilities=c_liab,
            working_capital=(c_assets - c_liab) if c_assets and c_liab else None,
            debt=debt_val,
            operating_cash_flow=ocf,
            capex=capex,
            gross_profit=gross_profit,
            cogs=None,
            retained_earnings=self._to_crores(_get_attr("retained_earnings")),
            interest_income=interest_income,
            interest_expense=interest_expense,
            total_income=total_income,
            non_interest_income=non_interest_income,
            gross_npa=gross_npa,
            net_npa=net_npa,
            total_advances=total_advances,
            provisions=provisions,
            total_deposits=total_deposits,
            car=car,
            cash_and_cash_equivalents=cash_ce,
            total_debt=actual_debt,
            depreciation_amortization=self._to_crores(_get_attr("depreciation_amortization")),
            share_capital=share_cap,
            face_value=fv,
            source="nse_xbrl",
            source_url=_get_attr("xbrl_url", ""),
            source_type="nse_xbrl",
            consolidated=_get_attr("is_consolidated", True),
            unit="INR_Crores",
        )

        return True

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        if not date_str:
            return None
        clean_str = str(date_str).strip()
        for fmt in ["%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"]:
            try:
                return datetime.strptime(clean_str, fmt)
            except ValueError:
                pass
        try:
            return pd.to_datetime(clean_str).to_pydatetime()
        except Exception:
            return None

    def _refresh_ttm(self, symbol: str):
        q_df = get_latest_quarterly_reports(symbol, limit=4)
        if q_df.empty:
            return
        records = q_df.to_dict("records")
        if len(records) >= 4:
            ttm_dict = self.calculator.compute_ttm(records)
            save_ttm_record(symbol, ttm_dict, source="nse_xbrl")

    def get_quarterly_financials(self, symbol: str) -> pd.DataFrame:
        self.ensure_data(symbol)
        df = get_latest_quarterly_reports(symbol, limit=8)
        return self._reports_to_income_df(df)

    def get_annual_financials(self, symbol: str) -> pd.DataFrame:
        self.ensure_data(symbol)
        df = get_latest_annual_reports(symbol, limit=5)
        return self._reports_to_income_df(df)

    def get_quarterly_balance_sheet(self, symbol: str) -> pd.DataFrame:
        self.ensure_data(symbol)
        df = get_latest_quarterly_reports(symbol, limit=8)
        return self._reports_to_balance_df(df)

    def get_annual_balance_sheet(self, symbol: str) -> pd.DataFrame:
        self.ensure_data(symbol)
        df = get_latest_annual_reports(symbol, limit=5)
        return self._reports_to_balance_df(df)

    def get_quarterly_cashflow(self, symbol: str) -> pd.DataFrame:
        self.ensure_data(symbol)
        df = get_latest_quarterly_reports(symbol, limit=8)
        return self._reports_to_cashflow_df(df)

    def get_annual_cashflow(self, symbol: str) -> pd.DataFrame:
        self.ensure_data(symbol)
        df = get_latest_annual_reports(symbol, limit=5)
        return self._reports_to_cashflow_df(df)

    def get_source(self) -> str:
        return "nse_xbrl"

    def ensure_data(self, symbol: str):
        # Purge any stale non-NSE-sourced data so we never serve
        # screener.in or yfinance fallback data as official NSE data.
        # Only runs once per session (subsequent calls are no-ops since
        # NSE-sourced data is preserved by the filter).
        if not self._nse_purged:
            purge_non_nse_reports()
            self._nse_purged = True
        q_df = get_latest_quarterly_reports(symbol, limit=1)
        a_df = get_latest_annual_reports(symbol, limit=1)
        if q_df.empty or a_df.empty:
            self.ingest_from_nse(symbol)
        # Data comes ONLY from NSE official XBRL filings.
        # No third-party (screener.in) fallback is used for fundamental data.

    def _reports_to_income_df(self, reports: pd.DataFrame) -> pd.DataFrame:
        if reports.empty:
            return pd.DataFrame()
        rows = []
        for _, row in reports.iterrows():
            period_str = f"Q{row.get('quarter', 1)} FY{row.get('financial_year', 2024)}"
            rows.append({
                "Period": period_str,
                "Revenue": row.get("revenue"),
                "Operating Profit": row.get("operating_profit"),
                "EBIT": row.get("ebit"),
                "Net Profit": row.get("pat"),
                "EPS": row.get("eps"),
            })
        return pd.DataFrame(rows).set_index("Period").T

    def _reports_to_balance_df(self, reports: pd.DataFrame) -> pd.DataFrame:
        if reports.empty:
            return pd.DataFrame()
        rows = []
        for _, row in reports.iterrows():
            period_str = f"FY{row.get('financial_year', 2024)}"
            rows.append({
                "Period": period_str,
                "Total Equity": row.get("equity"),
                "Total Assets": row.get("assets"),
                "Total Liabilities": row.get("liabilities"),
                "Current Assets": row.get("current_assets"),
                "Current Liabilities": row.get("current_liabilities"),
                "Total Debt": row.get("debt"),
            })
        return pd.DataFrame(rows).set_index("Period").T

    def _reports_to_cashflow_df(self, reports: pd.DataFrame) -> pd.DataFrame:
        if reports.empty:
            return pd.DataFrame()
        rows = []
        for _, row in reports.iterrows():
            period_str = f"FY{row.get('financial_year', 2024)}"
            rows.append({
                "Period": period_str,
                "Operating Cash Flow": row.get("operating_cash_flow"),
                "CapEx": row.get("capex"),
            })
        return pd.DataFrame(rows).set_index("Period").T

    def build_fundamentals_dict(self, symbol: str) -> Dict[str, Any]:
        self.ensure_data(symbol)
        info = self.get_company_info(symbol)

        q_reports = get_latest_quarterly_reports(symbol, limit=8)
        a_reports = get_latest_annual_reports(symbol, limit=5)
        ttm_rec = get_ttm_record(symbol)

        q_list = q_reports.to_dict("records") if not q_reports.empty else []
        a_list = a_reports.to_dict("records") if not a_reports.empty else []

        latest_q = q_list[0] if q_list else {}
        latest_a = a_list[0] if a_list else {}

        ratios = self.calculator.compute_all_ratios(latest_q, latest_a, ttm_rec or {})
        q_growth = self.calculator.compute_quarterly_growth(q_list)
        a_growth = self.calculator.compute_annual_growth(a_list)

        piotroski = self.calculator.compute_piotroski(a_list) if len(a_list) >= 2 else None
        altman = self.calculator.compute_altman(latest_a)

        rev = latest_q.get("revenue") or latest_a.get("revenue")
        pat = latest_q.get("pat") or latest_a.get("pat")
        eps = latest_q.get("eps") or latest_a.get("eps")
        ebit = latest_q.get("ebit") or latest_a.get("ebit")

        # Depreciation & Amortisation from official filings (annual preferred, quarterly fallback)
        dda_val = latest_a.get("depreciation_amortization") or latest_q.get("depreciation_amortization")
        # TTM EBIT from the TTM record or annual filing
        ttm_ebit_val = (ttm_rec.get("ebit") if ttm_rec else None) or latest_a.get("ebit") or latest_q.get("ebit")

        # Derive shares outstanding from official filing data:
        # Equity Share Capital / Face Value per Share
        shares_out = info.get("sharesOutstanding")
        if not shares_out:
            share_cap = latest_a.get("share_capital") or latest_q.get("share_capital")
            face_val = latest_a.get("face_value") or latest_q.get("face_value")
            if share_cap is not None and face_val is not None and face_val > 0:
                # share_cap is in crores (INR Crores), face_val is INR per share
                # shares = share_cap (crores) × 1e7 / face_value
                shares_out = (float(share_cap) * 1e7) / float(face_val)

        mcap = info.get("market_cap")
        if not mcap:
            try:
                from data.database import get_company_info as db_get_company_info
                cached = db_get_company_info(symbol)
                if cached and cached.get("market_cap"):
                    mcap = float(cached["market_cap"])
            except Exception:
                pass
        # Fallback: Market Cap = Current Price × Shares Outstanding
        # Price: OHLCV only from price feed (yfinance download) — compliant
        # Shares: from official NSE XBRL filing (Equity Share Capital / Face Value) — compliant
        if not mcap and shares_out and shares_out > 0:
            try:
                from data.fetch_prices import fetch_prices
                prices = fetch_prices(symbol, period="5d")
                if not prices.empty and "Close" in prices.columns:
                    prices = prices.dropna(subset=["Close"])
                    if not prices.empty:
                        current_price = float(prices["Close"].iloc[-1])
                        if current_price > 0:
                            mcap = round((current_price * shares_out) / 1e7, 2)
            except Exception:
                pass

        if mcap:
            info["market_cap"] = mcap
            latest_q["market_cap"] = mcap
            latest_a["market_cap"] = mcap
            ratios = self.calculator.compute_all_ratios(latest_q, latest_a, ttm_rec or {})

        eps_g = q_growth.get("eps_qoq") or a_growth.get("eps_yoy")
        peg = self.calculator.compute_peg(ratios.get("pe"), eps_g)

        # Compute TTM EPS and TTM PAT for accurate P/E (sum of 4 distinct quarterly filings)
        ttm_eps = None
        ttm_pat = None
        if q_list:
            eps_vals = []
            pat_vals = []
            seen_periods = set()
            # Deduplicate by report_date to ensure 4 DISTINCT quarterly filings
            for rec in q_list[:8]:
                period_key = str(rec.get("report_date", ""))
                if not period_key or period_key in seen_periods:
                    continue
                seen_periods.add(period_key)
                v_eps = rec.get("eps")
                if v_eps is not None and not (isinstance(v_eps, float) and v_eps != v_eps):
                    eps_vals.append(float(v_eps))
                v_pat = rec.get("pat")
                if v_pat is not None and not (isinstance(v_pat, float) and v_pat != v_pat):
                    pat_vals.append(float(v_pat))
            # Only compute TTM if we have 4 distinct quarterly filings
            if len(eps_vals) >= 4:
                ttm_eps = sum(eps_vals[:4])
            if len(pat_vals) >= 4:
                ttm_pat = sum(pat_vals[:4])

        # Compute PE = MarketCap (Cr) / TTM PAT (Cr) — both in crores
        pe_ratio = ratios.get("pe")
        if mcap and ttm_pat is not None and ttm_pat > 0:
            pe_ratio = round(float(mcap) / ttm_pat, 2)
        elif mcap and ttm_eps is not None and ttm_eps > 0:
            # Fallback: use price per share / TTM EPS if shares outstanding is known
            shares = q_list[0].get("shares_outstanding") if q_list else None
            if shares is not None and float(shares) > 0:
                price_per_share = (float(mcap) * 1e7) / float(shares)
                pe_ratio = round(price_per_share / ttm_eps, 2)

        # Compute annual free cash flow = OCF + CapEx (where CapEx is negative cash flow)
        fcf_annual = None
        if latest_a:
            ocf_a = self.calculator._safe(latest_a.get("operating_cash_flow"))
            cap_a = self.calculator._safe(latest_a.get("capex"))
            if ocf_a is not None and cap_a is not None:
                fcf_annual = self.calculator.compute_fcf(ocf_a, cap_a)

        # Retrieve shareholding from official NSE shareholder disclosures
        sh_info = self.get_shareholding(symbol)

        # Compute banking metrics if the company is a financial institution
        is_bank = any(b.lower() in (info.get("sector") or "").lower()
                      for b in {"Financial Services", "Banking", "Finance", "Insurance"})
        bank_metrics = {}
        if is_bank:
            bank_income = {}
            bank_balance = {}
            for rec in [latest_a, latest_q]:
                if rec:
                    bank_income = {
                        **bank_income,
                        "Interest_Income": rec.get("interest_income"),
                        "Interest_Expense": rec.get("interest_expense"),
                        "Total_Income": rec.get("total_income"),
                        "Non_Interest_Income": rec.get("non_interest_income"),
                        "ROA": rec.get("roa"),
                        "ROE": rec.get("roe"),
                    }
                    bank_balance = {
                        **bank_balance,
                        "Gross_NPA": rec.get("gross_npa"),
                        "Net_NPA": rec.get("net_npa"),
                        "Total_Advances": rec.get("total_advances"),
                        "Provisions": rec.get("provisions"),
                        "Total_Deposits": rec.get("total_deposits"),
                        "CAR": rec.get("car"),
                    }
            bank_metrics = compute_banking_metrics(bank_income, bank_balance)

        # Build metric_details lineage dict (used by UI helper for source attribution)
        def _make_detail(metric_name, val, rec):
            if not rec:
                rec = {}
            p_type = rec.get("period") or "N/A"
            q = rec.get("quarter")
            fy = rec.get("financial_year")
            if q and fy:
                q_fy = f"Q{q} FY{fy}"
            elif fy:
                q_fy = f"FY{fy}"
            elif q:
                q_fy = f"Q{q}"
            else:
                q_fy = "N/A"
            r_date = rec.get("report_date") or "N/A"
            c_name = rec.get("company") or info.get("company_name") or symbol
            is_c = bool(rec.get("consolidated", 1)) if rec else True
            u_str = rec.get("unit") or "INR_Crores"
            s_url = rec.get("source_url") or "N/A"
            s_type = rec.get("source_type") or "nse_xbrl"
            safe_val = FinancialCalculator._safe(val) if val is not None else None
            return {
                "metric": metric_name,
                "company": c_name,
                "ticker": symbol,
                "period": p_type,
                "quarter_or_year": q_fy,
                "report_date": r_date,
                "consolidated": "Consolidated" if is_c else "Standalone",
                "is_consolidated": is_c,
                "value": safe_val,
                "unit": u_str,
                "source_url": s_url,
                "source_type": s_type,
            }

        target_rec = latest_q or latest_a
        target_a_rec = latest_a or latest_q

        metric_details = {
            "Revenue": _make_detail("Revenue", rev, target_rec),
            "PAT": _make_detail("PAT", pat, target_rec),
            "EPS": _make_detail("EPS", eps, target_rec),
            "EBIT": _make_detail("EBIT", ebit, target_rec),
            "ROE": _make_detail("ROE", ratios.get("roe"), target_rec),
            "ROCE": _make_detail("ROCE", ratios.get("roce"), target_rec),
            "ROA": _make_detail("ROA", ratios.get("roa"), target_rec),
            "DebtEquity": _make_detail("DebtEquity", ratios.get("debt_equity"), target_rec),
            "OPM": _make_detail("OPM", ratios.get("opm"), target_rec),
            "NPM": _make_detail("NPM", ratios.get("npm"), target_rec),
            "FreeCashFlow": _make_detail("FreeCashFlow", ratios.get("fcf") or fcf_annual, target_rec),
            "PE": _make_detail("PE", pe_ratio, target_rec),
            "PEG": _make_detail("PEG", peg, target_rec),
            "Piotroski": _make_detail("Piotroski", piotroski.get("score") if isinstance(piotroski, dict) else None, target_a_rec),
            "Altman": _make_detail("Altman", altman.get("value") if isinstance(altman, dict) else None, target_rec),
        }

        piotroski_score = piotroski.get("score") if isinstance(piotroski, dict) else None
        altman_value = altman.get("value") if isinstance(altman, dict) else None
        altman_available = altman.get("available", False) if isinstance(altman, dict) else False
        altman_dict = {"value": altman_value, "available": altman_available} if isinstance(altman, dict) else {"value": None, "available": False}

        ratios_q_full = self.calculator.compute_all_ratios(latest_q) if latest_q else {}

        qf = self.get_quarterly_financials(symbol)
        af = self.get_annual_financials(symbol)
        qbs = self.get_quarterly_balance_sheet(symbol)
        bs = self.get_annual_balance_sheet(symbol)
        cf = self.get_annual_cashflow(symbol)
        result = {
            "Symbol": symbol,
            "Company": info.get("company_name", symbol),
            "Sector": info.get("sector", "N/A"),
            "Industry": info.get("industry", "N/A"),
            "MarketCap": mcap,
            "PE": pe_ratio,
            "PEG": peg,
            "ForwardPE": None,
            "PriceSales": None,
            "ROE": ratios.get("roe"),
            "ROCE": ratios.get("roce"),
            "ROA": ratios.get("roa"),
            "RevenueGrowth": a_growth.get("revenue_growth") or q_growth.get("sales_yoy"),
            "Revenue_Growth": a_growth.get("revenue_growth") or q_growth.get("sales_yoy"),
            "EarningsGrowth": a_growth.get("eps_growth") or q_growth.get("eps_yoy"),
            "EPS_Growth": a_growth.get("eps_growth") or q_growth.get("eps_yoy"),
            "PAT_Growth": a_growth.get("pat_growth") or q_growth.get("pat_yoy"),
            "EarningsQuarterlyGrowth": q_growth.get("eps_yoy") or q_growth.get("eps_qoq"),
            "DebtEquity": ratios.get("debt_equity"),
            "Debt_Equity": ratios.get("debt_equity"),
            "ProfitMargin": ratios.get("npm"),
            "GrossMargin": ratios.get("gross_margin"),
            "GrossMargins": ratios.get("gross_margin"),
            "DividendYield": None,
            "NetIncome": pat,
            "TotalAssets": latest_q.get("assets") or latest_a.get("assets"),
            "TotalLiabilities": latest_q.get("liabilities") or latest_a.get("liabilities"),
            "TotalDebt": latest_a.get("total_debt") or latest_q.get("total_debt") or latest_a.get("debt") or latest_q.get("debt"),
            "TotalCash": latest_a.get("cash_and_cash_equivalents") or latest_q.get("cash_and_cash_equivalents"),
            "CashAndCashEquivalents": latest_a.get("cash_and_cash_equivalents") or latest_q.get("cash_and_cash_equivalents"),
            "CurrentAssets": latest_q.get("current_assets") or latest_a.get("current_assets"),
            "CurrentLiabilities": latest_q.get("current_liabilities") or latest_a.get("current_liabilities"),
            "TotalStockholderEquity": latest_q.get("equity") or latest_a.get("equity"),
            "WorkingCapital": latest_q.get("working_capital") or latest_a.get("working_capital"),
            "RetainedEarnings": latest_q.get("retained_earnings") or latest_a.get("retained_earnings"),
            "EBIT": ebit,
            "Revenue": rev,
            "PAT": pat,
            "EPS": eps,
            "TTMEPS": ttm_rec.get("eps") if ttm_rec else None,
            "OPM": ratios.get("opm"),
            "NPM": ratios.get("npm"),
            "OperatingCashFlow": ratios.get("fcf") or latest_q.get("operating_cash_flow") or latest_a.get("operating_cash_flow"),
            "OperatingCashFlowTTM": ttm_rec.get("operating_cash_flow") if ttm_rec else None,
            "OperatingCashFlowAnnual": latest_a.get("operating_cash_flow"),
            "FreeCashFlow": ratios.get("fcf") or fcf_annual,
            "FreeCashFlowTTM": ttm_rec.get("fcf") if ttm_rec else None,
            "FreeCashFlowAnnual": fcf_annual,
            "CurrentRatio": None,
            "QuickRatio": None,
            "BookValue": None,
            "SharesOutstanding": shares_out,
            "FloatShares": None,
            "InstitutionsPercentHeld": sh_info.get("Institutional_Pct"),
            "InsidersPercentHeld": sh_info.get("Promoter_Pct"),
            "Promoter_Pct": sh_info.get("Promoter_Pct"),
            "FII_Pct": sh_info.get("FII_Pct"),
            "DII_Pct": sh_info.get("DII_Pct"),
            "Govt_Pct": sh_info.get("Govt_Pct"),
            "Public_Pct": sh_info.get("Public_Pct"),
            "Institutional_Pct": sh_info.get("Institutional_Pct"),
            "Shareholders_Count": sh_info.get("Shareholders_Count"),
            "Shareholding_Period": sh_info.get("Shareholding_Period"),
            "Shareholding_Table": sh_info.get("Shareholding_Table"),
            "Shareholding_History": sh_info.get("Shareholding_History"),
            "SharesShort": None,
            "SharesShortPriorMonth": None,
            "TotalCash": latest_a.get("cash_and_cash_equivalents") or latest_q.get("cash_and_cash_equivalents"),
            "EBITDA": (ebit + dda_val) if (ebit and dda_val) else None,
            "EBITDATTM": (ttm_ebit_val + dda_val) if (ttm_ebit_val and dda_val) else None,
            "EnterpriseValue": None,
            "Piotroski": piotroski_score,
            "PiotroskiFScore": piotroski_score,
            "Piotroski_FScore": piotroski_score,
            "piotroski_f_score": piotroski,
            "Altman": altman,
            "AltmanZScore": altman_dict,
            "Altman_ZScore": altman_dict,
            "altman_z_score": altman,
            "Sales_QoQ": q_growth.get("sales_qoq"),
            "Sales_YoY": q_growth.get("sales_yoy"),
            "PAT_QoQ": q_growth.get("pat_qoq"),
            "PAT_YoY": q_growth.get("pat_yoy"),
            "EPS_QoQ": q_growth.get("eps_qoq"),
            "EPS_YoY": q_growth.get("eps_yoy"),
            "NIM": bank_metrics.get("NIM"),
            "NII": bank_metrics.get("NII"),
            "CASA_Ratio": bank_metrics.get("CASA_Ratio"),
            "GNPA": bank_metrics.get("GNPA"),
            "NNPA": bank_metrics.get("NNPA"),
            "PCR": bank_metrics.get("PCR"),
            "CAR": bank_metrics.get("CAR"),
            "quarterly_financials": qf if not qf.empty else pd.DataFrame(),
            "annual_financials": af if not af.empty else pd.DataFrame(),
            "quarterly_balance_sheet": qbs if not qbs.empty else pd.DataFrame(),
            "balance_sheet": bs if not bs.empty else pd.DataFrame(),
            "cashflow": cf if not cf.empty else pd.DataFrame(),
            "quarterly_roe": ratios_q_full.get("roe"),
            "quarterly_roa": ratios_q_full.get("roa"),
            "quarterly_debt_equity": ratios_q_full.get("debt_equity"),
            "quarterly_growth": q_growth,
            "annual_growth": a_growth,
            "piotroski_f_score": piotroski,
            "altman_z_score": altman,
            "metric_details": metric_details,
            "fundamentals_source": "nse_xbrl",
        }

        return result
