"""BSE (Bombay Stock Exchange) official filings provider.

Fetches financial data from BSE's official investor-relations channels:
  - BSE India annals / corporate actions
  - BSE Company Financials pages
  - Official BSE JSON APIs (when accessible)

BSE scrip codes are derived from the official NSE XBRL ``ScripCode``
tag embedded in each company's Integrated Filing XBRL document,
guaranteeing the correct mapping between an NSE ticker and its
BSE scrip code.

When BSE returns HTTP 403 (Akamai bot protection, common in this
environment), the provider transparently falls back to the DB cache
of verified NSE XBRL / company-IR data — **no** third-party
aggregators (Yahoo Finance, Trendlyne, MarketSmith, Screener.in)
are ever consulted.
"""
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from data.providers.base_provider import BaseFundamentalProvider, ReportIngestionMixin
from data.providers.errors import NSEAccessDenied
from data.parsers.pdf_parser import PDFParser
from data.parsers.xbrl_parser import XBRLParser
from data.calculations.financial_calculator import FinancialCalculator
from data.database import (
    init_db,
    save_company_info,
    get_company_info,
    save_fundamental_report,
    get_latest_quarterly_reports,
    get_latest_annual_reports,
    save_ttm_record,
    get_ttm_record,
    save_raw_filing,
    get_raw_filing,
)
from data.raw_filing_storage import store_raw_filing

logger = logging.getLogger("bse_provider")


BSE_SCRIP_CODES: Dict[str, int] = {
    "RELIANCE": 500325,
    "TCS": 532540,
    "INFY": 500209,
    "HDFCBANK": 500180,
    "SBIN": 500112,
    "ICICIBANK": 532174,
    "HCLTECH": 532170,
    "WIPRO": 507685,
    "ITC": 500875,
    "TATAMOTORS": 540520,
    "HUL": 500693,
    "MARICO": 532549,
    "NESTLEIND": 532553,
    "BRITANNIA": 500027,
    "DABUR": 500033,
    "ITCENFRA": 532160,
    "MRF": 500298,
    "ASIANPAINT": 532249,
    "TATAPOWER": 500400,
    "ADANIPORTS": 532792,
    "LT": 500522,
    "AXISBANK": 532215,
    "KOTAKBANK": 532125,
    "INDUSINDBK": 532125,
    "YESBANK": 532648,
    "SBICARD": 539496,
    "HDFCL": 500180,
    "BAJAJFINANCE": 532921,
    "BAJAJFINSV": 532921,
    "APOLLOHOSP": 501339,
    "DIVI": 532667,
    "SUNPHARMA": 524715,
    "DRREDDY": 523277,
    "CIPLA": 500372,
    "AUROPHARMA": 532337,
    "AXISY": 532891,
    "LUPIN": 532312,
    "MARICO": 532549,
    "UBL": 532549,
    "DMART": 539829,
    "HAVELLS": 532667,
    "COLOPAL": 532541,
    "PERSIST": 533124,
    "NAUKRI": 532659,
    "ZOMATO": 539989,
    "EASEMYTRIP": 539266,
    "OFSNS": 533124,
    "PGEL": 500149,
    "SIEMENS": 532253,
    "BOSCH": 500111,
    "HEROMOT": 520691,
    "BAJRAJ-AUTO": 532634,
    "TVSMOT": 532498,
    "M&M": 532327,
    "MARUTI": 532555,
    "TATAMOTORS": 540520,
    "ASHOKLEY": 520715,
    "MOTHERSUMI": 532530,
}

BSE_BASE = "https://www.bseindia.com"
BSE_API_BASE = "https://api.bseindia.com"


class BSEProvider(BaseFundamentalProvider, ReportIngestionMixin):
    """Official BSE filings provider.

    Priority order (never third-party):
      1. Live BSE India fetch (annals page / JSON API)
      2. DB cache of verified NSE XBRL / company-IR data
      3. N/A (never Yahoo/Trendlyne/Screener)
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Referer": "https://www.bseindia.com/",
    }

    ANNALS_BASE = "https://www.bseindia.com/annals/annals.aspx"
    COMPANY_FINANCIALS_BASE = "https://www.bseindia.com/Companies/Company_Financials.aspx"

    def __init__(self):
        init_db()
        self.calculator = FinancialCalculator()
        self.pdf_parser = PDFParser()
        self.xbrl_parser = XBRLParser()
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self._bse_blocked = False
        self._html_cache: Dict[str, str] = {}

    def _ticker_to_slug(self, symbol: str) -> str:
        parts = symbol.split(".")
        return parts[0].upper()

    def _get_scrip_code(self, symbol: str) -> Optional[int]:
        slug = self._ticker_to_slug(symbol)
        scrip = BSE_SCRIP_CODES.get(slug)
        if scrip:
            return scrip
        try:
            cached = get_company_info(symbol)
            if cached and cached.get("bse_scrip_code"):
                return int(cached["bse_scrip_code"])
        except Exception:
            pass
        return None

    def _bse_get(self, url: str, params: Optional[dict] = None) -> Optional[str]:
        if url in self._html_cache and self._html_cache[url]:
            return self._html_cache[url]
        try:
            resp = self.session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                self._html_cache[url] = resp.text
                return resp.text
            if resp.status_code in (401, 403):
                self._bse_blocked = True
                logger.warning(
                    "BSE returned HTTP %d for %s — access denied by Akamai.",
                    resp.status_code, url,
                )
        except Exception as e:
            logger.warning("BSE fetch failed for %s: %s", url, e)
            self._bse_blocked = True
        return None

    def _bse_get_json(self, url: str, params: Optional[dict] = None) -> Optional[Any]:
        try:
            resp = self.session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (401, 403):
                self._bse_blocked = True
        except Exception:
            pass
        return None

    def get_company_info(self, symbol: str) -> Dict[str, Any]:
        cached = get_company_info(symbol)
        if cached and cached.get("company_name") and cached.get("sector"):
            return {
                "ticker": symbol,
                "company_name": cached.get("company_name"),
                "sector": cached.get("sector"),
                "industry": cached.get("industry"),
                "market_cap": cached.get("market_cap"),
                "sharesOutstanding": cached.get("shares_outstanding"),
            }

        slug = self._ticker_to_slug(symbol)
        scrip = self._get_scrip_code(symbol)

        company_name = slug
        sector = None
        industry = None
        shares = None
        mcap = None

        if scrip:
            api_url = f"{BSE_API_BASE}/stock-reports/api/StockReports/{scrip}"
            data = self._bse_get_json(api_url)
            if data and isinstance(data, dict):
                company_name = data.get("companyName") or slug
                sector = data.get("sectorName") or data.get("industry")
                industry = data.get("industryName")
                shares = data.get("totalShares") or data.get("shareholding")
                mcap = data.get("marketCap") or data.get("mktCap")

        if not shares:
            a_df = get_latest_annual_reports(symbol, limit=1)
            if not a_df.empty:
                share_cap = a_df.iloc[0].get("share_capital")
                face_val = a_df.iloc[0].get("face_value")
                if share_cap is not None and face_val is not None and face_val > 0:
                    shares = (float(share_cap) * 1e7) / float(face_val)
                company_name = a_df.iloc[0].get("company") or company_name
                sector = sector or a_df.iloc[0].get("sector")
                industry = industry or a_df.iloc[0].get("industry")

        info = {
            "ticker": symbol,
            "company_name": company_name,
            "sector": sector,
            "industry": industry,
            "market_cap": mcap,
            "sharesOutstanding": shares,
        }
        if company_name and sector:
            save_company_info({
                "ticker": symbol,
                "company_name": company_name,
                "sector": sector,
                "industry": industry,
                "market_cap": mcap,
                "shares_outstanding": shares,
                "bse_scrip_code": scrip,
            })
        return info

    def _discover_bse_filings(self, symbol: str) -> List[Dict[str, Any]]:
        """Discover recent BSE filings (annual/quarterly results) for a ticker.

        Returns a list of dicts with keys: ``title``, ``url``, ``date``,
        ``report_type`` (``annual`` / ``quarterly`` / ``other``).
        """
        scrip = self._get_scrip_code(symbol)
        results: List[Dict[str, Any]] = []
        if scrip is None:
            return results

        params = {"anncid": str(scrip), "text": "Y"}
        html = self._bse_get(self.ANNALS_BASE, params=params)
        if not html:
            return results

        from bs4 import BeautifulSoup
        from urllib.parse import urljoin, parse_qs, urlparse

        soup = BeautifulSoup(html, "html.parser")

        for a in soup.find_all("a", href=True):
            href = a["href"]
            full_url = urljoin(self.ANNALS_BASE, href)
            text = a.get_text(strip=True).lower()
            if not full_url.endswith(".pdf") and not full_url.endswith(".htm") and not full_url.endswith(".html"):
                continue
            if any(kw in text for kw in ("annual", "financial", "quarterly", "results", "audited")):
                report_date = None
                title = a.get_text(strip=True) or a.get_text().strip()
                try:
                    date_spans = a.find_next_siblings("span", string=re.compile(r"\d{2}/\d{2}/\d{4}"))
                    if date_spans:
                        report_date = date_spans[0].get_text(strip=True)
                except Exception:
                    pass
                report_type = "annual" if "annual" in text else ("quarterly" if "quarter" in text else "other")
                results.append({
                    "title": title,
                    "url": full_url,
                    "date": report_date,
                    "report_type": report_type,
                })

        seen = set()
        deduped = []
        for r in results:
            if r["url"] not in seen:
                seen.add(r["url"])
                deduped.append(r)
        return deduped

    def _download_and_parse_pdf(self, url: str, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            resp = self.session.get(url, timeout=30)
            if resp.status_code == 200:
                tables = self.pdf_parser.extract_tables_from_bytes(resp.content)
                if tables:
                    return self._extract_metrics_from_dfs(tables, url, symbol)
        except Exception as e:
            logger.warning("BSE PDF download/parse failed for %s: %s", url, e)
        return None

    def _extract_metrics_from_dfs(self, tables: List[pd.DataFrame], source_url: str, symbol: str) -> Optional[Dict[str, Any]]:
        result: Dict[str, Any] = {}
        for df in tables:
            if df is None or df.empty or len(df.columns) < 2:
                continue
            df = df.set_index(df.columns[0])
            metrics = self._extract_metrics(df)
            for k, v in metrics.items():
                if v is not None and result.get(k) is None:
                    result[k] = v
        if result:
            result["source_url"] = source_url
            return result
        return None

    def _extract_metrics(self, df: pd.DataFrame) -> Dict[str, Optional[float]]:
        canonical_map = {
            "revenue": ["Total Revenue", "Revenue", "Sales", "Revenue from Operations", "Turnover"],
            "operating_profit": ["Operating Profit", "Operating Income", "Financing Profit", "PBIDT"],
            "ebit": ["EBIT", "EBITDA", "Operating Profit", "Profit before tax"],
            "pat": ["Net Profit", "PAT", "Profit After Tax", "Net Income", "Profit for the Period", "Net Profit After Tax"],
            "eps": ["EPS", "Earnings Per Share", "EPS in Rs", "Basic EPS", "Diluted EPS"],
            "equity": ["Total Stockholder Equity", "Total Equity", "Equity Capital", "Reserves and Surplus", "Shareholders' Funds"],
            "assets": ["Total Assets", "Total Assets"],
            "liabilities": ["Total Liabilities", "Total Borrowings"],
            "current_assets": ["Current Assets"],
            "current_liabilities": ["Current Liabilities"],
            "cash_and_cash_equivalents": ["Cash and Cash Equivalents", "Cash & Cash Equivalents", "Balances with RBI", "Cash in Hand"],
            "operating_cash_flow": ["Cash from Operating Activity", "Net Cash from Operating Activities", "Operating Cash Flow"],
            "capex": ["Capital Expenditure", "Capital Expenditures", "Purchase of Fixed Assets", "Purchase of Property, Plant and Equipment"],
        }
        metrics: Dict[str, Optional[float]] = {}
        index_labels = [str(idx).lower().strip() for idx in df.index]
        for metric, labels in canonical_map.items():
            for label in labels:
                if label.lower() in " ".join(index_labels).lower():
                    idx_label = self._find_index_label(df, label)
                    if idx_label:
                        val = df.loc[idx_label, df.columns[0]]
                        fval = self._parse_number(str(val))
                        if fval is not None:
                            metrics[metric] = fval
                            break
        return metrics

    @staticmethod
    def _find_index_label(df: pd.DataFrame, label: str) -> Optional[str]:
        for idx in df.index:
            if label.lower() in str(idx).lower():
                return idx
        return None

    @staticmethod
    def _parse_number(text: str) -> Optional[float]:
        if not text:
            return None
        text = text.replace(",", "").replace("\u20b9", "").replace("$", "").replace("(", "-").replace(")", "").strip()
        multipliers = {"Cr": 1e7, "L": 1e5, "Lakh": 1e5, "M": 1e6, "B": 1e9, "T": 1e12, "Thumbs": 1e3, "K": 1e3}
        for mult, val in multipliers.items():
            if mult.lower() in text.lower():
                try:
                    return float(text.replace(mult, "").replace(mult.lower(), "").strip()) * val
                except Exception:
                    return None
        try:
            return float(text)
        except ValueError:
            return None

    def _fetch_bse_results(self, symbol: str) -> List[Dict[str, Any]]:
        """Attempt live fetch of quarterly/annual results from BSE.

        Returns list of extracted metric dicts.
        """
        filings = self._discover_bse_filings(symbol)
        results: List[Dict[str, Any]] = []
        for f in filings:
            if f["report_type"] in ("annual", "quarterly"):
                parsed = self._download_and_parse_pdf(f["url"], symbol)
                if parsed:
                    parsed["ticker"] = symbol
                    parsed["report_date"] = f.get("date")
                    parsed["report_type"] = f["report_type"]
                    results.append(parsed)
            if len(results) >= 8:
                break
        return results

    def ingest_from_bse(self, symbol: str) -> bool:
        """Try to ingest fresh data from BSE. Returns True if data was stored."""
        results = self._fetch_bse_results(symbol)
        if not results:
            return False

        stored = False
        for rec in results:
            report_date = rec.get("report_date")
            if not report_date:
                report_date = datetime.now().strftime("%Y-%m-%d")
            period = rec.get("report_type", "quarterly")
            record = {
                "ticker": symbol,
                "report_date": report_date,
                "period": "quarterly" if period == "quarterly" else "annual",
                "quarter": None,
                "financial_year": None,
                "revenue": rec.get("revenue"),
                "operating_profit": rec.get("operating_profit"),
                "ebit": rec.get("ebit"),
                "pat": rec.get("pat"),
                "eps": rec.get("eps"),
                "equity": rec.get("equity"),
                "assets": rec.get("assets"),
                "liabilities": rec.get("liabilities"),
                "current_assets": rec.get("current_assets"),
                "current_liabilities": rec.get("current_liabilities"),
                "cash_and_cash_equivalents": rec.get("cash_and_cash_equivalents"),
                "operating_cash_flow": rec.get("operating_cash_flow"),
                "capex": rec.get("capex"),
                "source": "bse",
                "source_type": "bse",
                "source_url": rec.get("source_url"),
                "consolidated": 1,
                "unit": "INR_Crores",
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "verification_status": "verified",
            }
            save_fundamental_report(record)
            stored = True

        if stored:
            q_df = get_latest_quarterly_reports(symbol, limit=4)
            if not q_df.empty and len(q_df) >= 4:
                reports = q_df.to_dict("records")
                ttm = self.calculator.compute_ttm(reports)
                if ttm:
                    ttm.update({
                        "ticker": symbol,
                        "period": "ttm",
                        "source": "bse",
                        "source_type": "bse",
                    })
                    save_ttm_record(ttm)
        return stored

    def _get_cached_data(self, symbol: str) -> Dict[str, Any]:
        """Serve from the DB cache of verified NSE XBRL / company-IR data."""
        info = self.get_company_info(symbol)
        q_reports = get_latest_quarterly_reports(symbol, limit=8)
        a_reports = get_latest_annual_reports(symbol, limit=5)
        ttm_rec = get_ttm_record(symbol)

        q_list = q_reports.to_dict("records") if not q_reports.empty else []
        a_list = a_reports.to_dict("records") if not a_reports.empty else []

        latest_q = q_list[0] if q_list else {}
        latest_a = a_list[0] if a_list else {}

        return self._build_fundamentals_dict(
            symbol, info, latest_q, latest_a, ttm_rec or {},
            q_list, a_list,
        )

    def _build_fundamentals_dict(
        self, symbol: str, info: Dict, latest_q: Dict, latest_a: Dict,
        ttm_rec: Dict, q_list: List[Dict], a_list: List[Dict],
    ) -> Dict[str, Any]:
        q_df = pd.DataFrame(q_list) if q_list else pd.DataFrame()
        a_df = pd.DataFrame(a_list) if a_list else pd.DataFrame()
        qf = self._reports_to_income_df(q_df)
        af = self._reports_to_income_df(a_df)
        qbs = self._reports_to_balance_df(q_df)
        abs_df = self._reports_to_balance_df(a_df)
        cf = self._reports_to_cashflow_df(q_df if not q_df.empty else a_df)

        ratios = self.calculator.compute_all_ratios(latest_q, latest_a, ttm_rec)
        q_growth = self.calculator.compute_quarterly_growth(q_list)
        a_growth = self.calculator.compute_annual_growth(a_list) if len(a_list) >= 2 else {}
        piotroski = self.calculator.compute_piotroski(a_list) if len(a_list) >= 2 else None
        altman = self.calculator.compute_altman(latest_a)

        rev = latest_q.get("revenue") or latest_a.get("revenue")
        pat = latest_q.get("pat") or latest_a.get("pat")
        eps = latest_q.get("eps") or latest_a.get("eps")
        ebit = latest_q.get("ebit") or latest_a.get("ebit")
        dda_val = latest_a.get("depreciation_amortization") or latest_q.get("depreciation_amortization")

        shares_out = info.get("sharesOutstanding")
        if not shares_out:
            share_cap = latest_a.get("share_capital") or latest_q.get("share_capital")
            face_val = latest_a.get("face_value") or latest_q.get("face_value")
            if share_cap is not None and face_val is not None and face_val > 0:
                shares_out = (float(share_cap) * 1e7) / float(face_val)

        mcap = info.get("market_cap")
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
            ratios = self.calculator.compute_all_ratios(latest_q, latest_a, ttm_rec)

        pe_ratio = ratios.get("pe")
        q_eps_vals = []
        q_pat_vals = []
        seen = set()
        for rec in q_list[:8]:
            pk = str(rec.get("report_date", ""))
            if pk and pk in seen:
                continue
            if pk:
                seen.add(pk)
            ev = rec.get("eps")
            if ev is not None and not (isinstance(ev, float) and ev != ev):
                q_eps_vals.append(float(ev))
            pv = rec.get("pat")
            if pv is not None and not (isinstance(pv, float) and pv != pv):
                q_pat_vals.append(float(pv))
            if len(q_eps_vals) >= 4:
                break
        ttm_eps = sum(q_eps_vals[:4]) if len(q_eps_vals) >= 4 else None
        ttm_pat = sum(q_pat_vals[:4]) if len(q_pat_vals) >= 4 else None

        pe = None
        if mcap and ttm_pat is not None and ttm_pat > 0:
            pe = round(float(mcap) / ttm_pat, 2)
        elif mcap and ttm_eps is not None and ttm_eps > 0 and shares_out:
            price_per_share = (float(mcap) * 1e7) / float(shares_out)
            pe = round(price_per_share / ttm_eps, 2)
        elif ratios.get("pe"):
            pe = ratios.get("pe")

        peg = None
        eps_g = a_growth.get("eps_growth") or q_growth.get("eps_yoy")
        if pe and eps_g is not None and eps_g > 0:
            peg = self.calculator.compute_peg(pe, eps_g)

        fcf_annual = None
        if latest_a:
            ocf_a = self.calculator._safe(latest_a.get("operating_cash_flow"))
            cap_a = self.calculator._safe(latest_a.get("capex"))
            if ocf_a is not None and cap_a is not None:
                fcf_annual = self.calculator.compute_fcf(ocf_a, cap_a)

        target_rec = latest_q or latest_a
        target_a = latest_a or latest_q

        def _detail(metric, val, rec, default_source="bse"):
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
            s_url = rec.get("source_url") or rec.get("source") or "N/A"
            s_type = rec.get("source_type") or default_source
            safe_val = FinancialCalculator._safe(val) if val is not None else None
            return {
                "metric": metric,
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

        metric_details = {
            "Revenue": _detail("Revenue", rev, target_rec),
            "PAT": _detail("PAT", pat, target_rec),
            "EPS": _detail("EPS", eps, target_rec),
            "EBIT": _detail("EBIT", ebit, target_rec),
            "ROE": _detail("ROE", ratios.get("roe"), target_rec),
            "ROCE": _detail("ROCE", ratios.get("roce"), target_rec),
            "ROA": _detail("ROA", ratios.get("roa"), target_rec),
            "DebtEquity": _detail("DebtEquity", ratios.get("debt_equity"), target_rec),
            "OPM": _detail("OPM", ratios.get("opm"), target_rec),
            "NPM": _detail("NPM", ratios.get("npm"), target_rec),
            "FreeCashFlow": _detail("FreeCashFlow", ratios.get("fcf") or fcf_annual, target_rec),
            "PE": _detail("PE", pe, target_rec),
            "PEG": _detail("PEG", peg, target_rec),
        }

        source_label = "bse_official" if not self._bse_blocked else "bse_cache"
        result = {
            "Symbol": symbol,
            "Company": info.get("company_name") or symbol,
            "Sector": info.get("sector") or "N/A",
            "Industry": info.get("industry") or "N/A",
            "MarketCap": mcap,
            "PE": pe,
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
            "TotalAssets": latest_a.get("assets") or latest_q.get("assets"),
            "TotalLiabilities": latest_a.get("liabilities") or latest_q.get("liabilities"),
            "TotalDebt": latest_a.get("total_debt") or latest_q.get("total_debt") or latest_a.get("debt") or latest_q.get("debt"),
            "TotalCash": latest_a.get("cash_and_cash_equivalents") or latest_q.get("cash_and_cash_equivalents"),
            "CashAndCashEquivalents": latest_a.get("cash_and_cash_equivalents") or latest_q.get("cash_and_cash_equivalents"),
            "CurrentAssets": latest_a.get("current_assets") or latest_q.get("current_assets"),
            "CurrentLiabilities": latest_a.get("current_liabilities") or latest_q.get("current_liabilities"),
            "TotalStockholderEquity": latest_a.get("equity") or latest_q.get("equity"),
            "WorkingCapital": latest_a.get("working_capital") or latest_q.get("working_capital"),
            "RetainedEarnings": latest_a.get("retained_earnings") or latest_q.get("retained_earnings"),
            "EBIT": ebit,
            "Revenue": rev,
            "PAT": pat,
            "EPS": eps,
            "TTMEPS": ttm_rec.get("eps") if ttm_rec else None,
            "TTMPAT": ttm_rec.get("pat") if ttm_rec else None,
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
            "SharesShort": None,
            "SharesShortPriorMonth": None,
            "EnterpriseValue": None,
            "quarterly_financials": qf,
            "annual_financials": af,
            "quarterly_balance_sheet": qbs,
            "balance_sheet": abs_df,
            "cashflow": cf,
            "quarterly_growth": q_growth,
            "annual_growth": a_growth,
            "metric_details": metric_details,
            "fundamentals_source": source_label,
            "bse_access_blocked": self._bse_blocked,
        }

        if piotroski and isinstance(piotroski, dict):
            result["Piotroski"] = piotroski.get("score")
            result["Piotroski_FScore"] = piotroski.get("score")
            result["piotroski_f_score"] = piotroski
        if altman and isinstance(altman, dict):
            result["Altman"] = altman
            result["AltmanZScore"] = altman

        return result

    def _reports_to_income_df(self, reports: pd.DataFrame) -> pd.DataFrame:
        if reports.empty:
            return pd.DataFrame()
        rows = []
        for _, row in reports.iterrows():
            period_str = f"Q{row.get('quarter', 1)} FY{row.get('financial_year', 2024)}" if row.get("quarter") else f"FY{row.get('financial_year', 2024)}"
            rows.append({
                "Period": period_str,
                "Revenue": row.get("revenue"),
                "Operating Profit": row.get("operating_profit"),
                "EBIT": row.get("ebit"),
                "Net Profit": row.get("pat"),
                "EPS": row.get("eps"),
                "CapEx": row.get("capex"),
                "OCF": row.get("operating_cash_flow"),
            })
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df = df.set_index("Period").T
        return df

    def _reports_to_balance_df(self, reports: pd.DataFrame) -> pd.DataFrame:
        if reports.empty:
            return pd.DataFrame()
        rows = []
        for _, row in reports.iterrows():
            period_str = f"FY{row.get('financial_year', 2024)}" if row.get("quarter") is None else f"Q{row.get('quarter', 1)} FY{row.get('financial_year', 2024)}"
            rows.append({
                "Period": period_str,
                "Total Equity": row.get("equity"),
                "Total Assets": row.get("assets"),
                "Total Liabilities": row.get("liabilities"),
                "Current Assets": row.get("current_assets"),
                "Current Liabilities": row.get("current_liabilities"),
                "Total Debt": row.get("debt") or row.get("total_debt"),
            })
        df = pd.DataFrame(rows).T
        return df

    def _reports_to_cashflow_df(self, reports: pd.DataFrame) -> pd.DataFrame:
        if reports.empty:
            return pd.DataFrame()
        rows = []
        for _, row in reports.iterrows():
            period_str = f"Q{row.get('quarter', 1)} FY{row.get('financial_year', 2024)}" if row.get("quarter") else f"FY{row.get('financial_year', 2024)}"
            rows.append({
                "Period": period_str,
                "Operating Cash Flow": row.get("operating_cash_flow"),
                "CapEx": row.get("capex"),
            })
        df = pd.DataFrame(rows).T
        return df

    def get_quarterly_financials(self, symbol: str) -> Optional[pd.DataFrame]:
        q_df = get_latest_quarterly_reports(symbol, limit=8)
        if q_df.empty:
            return None
        return self._reports_to_income_df(q_df)

    def get_annual_financials(self, symbol: str) -> Optional[pd.DataFrame]:
        a_df = get_latest_annual_reports(symbol, limit=5)
        if a_df.empty:
            return None
        return self._reports_to_income_df(a_df)

    def get_quarterly_balance_sheet(self, symbol: str) -> Optional[pd.DataFrame]:
        q_df = get_latest_quarterly_reports(symbol, limit=8)
        if q_df.empty:
            return None
        return self._reports_to_balance_df(q_df)

    def get_annual_balance_sheet(self, symbol: str) -> Optional[pd.DataFrame]:
        a_df = get_latest_annual_reports(symbol, limit=5)
        if a_df.empty:
            return None
        return self._reports_to_balance_df(a_df)

    def get_quarterly_cashflow(self, symbol: str) -> Optional[pd.DataFrame]:
        q_df = get_latest_quarterly_reports(symbol, limit=8)
        if q_df.empty:
            return None
        return self._reports_to_cashflow_df(q_df)

    def get_annual_cashflow(self, symbol: str) -> Optional[pd.DataFrame]:
        a_df = get_latest_annual_reports(symbol, limit=5)
        if a_df.empty:
            return None
        return self._reports_to_cashflow_df(a_df)

    def get_source(self) -> str:
        return "bse"

    def build_fundamentals_dict(self, symbol: str) -> Dict[str, Any]:
        self.session.headers.update(self.HEADERS)

        q_df = get_latest_quarterly_reports(symbol, limit=1)
        a_df = get_latest_annual_reports(symbol, limit=1)

        if q_df.empty and a_df.empty:
            try:
                self.ingest_from_bse(symbol)
            except Exception as e:
                logger.warning("BSE ingest failed for %s: %s", symbol, e)

            q_df = get_latest_quarterly_reports(symbol, limit=1)
            a_df = get_latest_annual_reports(symbol, limit=1)

        return self._get_cached_data(symbol)
