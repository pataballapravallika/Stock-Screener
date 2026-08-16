"""Official company reports provider — fetches financial data exclusively
from official company investor-relations (IR) web pages, annual reports,
and quarterly result PDFs hosted on each company's own domain.

NO third-party sites (Yahoo Finance, Trendlyne, MarketSmith, Screener.in)
are used.  Only:
  - Official company investor-relations pages
  - Official company annual reports (PDF)
  - Official company quarterly results (PDF)
  - Official XBRL / HTML filings

Every stored metric retains:
  - source URL          (company IR page or PDF link)
  - source type         ("company_ir")
  - report date
  - quarter / fiscal year
  - consolidated / standalone
  - unit                ("INR_Crores")
  - verification_status
"""
import logging
import math
import os
import re
import sys
import time
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import requests

from data.providers.base_provider import BaseFundamentalProvider, ReportIngestionMixin
from data.parsers.pdf_parser import PDFParser
from data.parsers.xbrl_parser import XBRLParser
from data.calculations.financial_calculator import FinancialCalculator
from data.database import (
    init_db, save_company_info, get_company_info,
    save_fundamental_report, get_latest_quarterly_reports,
    get_latest_annual_reports, save_ttm_record, get_ttm_record,
    save_raw_filing,
)
from data.raw_filing_storage import store_raw_filing

logger = logging.getLogger("official_reports_provider")


class OfficialReportsProvider(BaseFundamentalProvider, ReportIngestionMixin):
    """Official company reports provider.

    Supported ingestion formats:
      - Official company investor-relations pages (HTML)
      - Official company annual report PDFs (local file or URL)
      - Official XBRL / inline documents (local file or URL)
      - Official company quarterly result PDFs (URL or local file)
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    INCOME_LABEL_RENAME = {
        "Sales+": "Total Revenue",
        "Sales": "Total Revenue",
        "Revenue": "Total Revenue",
        "Operating Revenue": "Total Revenue",
        "Total Sales": "Total Revenue",
        "Revenue from Operations": "Total Revenue",
        "Net Profit": "Net Income",
        "Profit After Tax": "Net Income",
        "Net Profit After Tax": "Net Income",
        "Profit For The Period": "Net Income",
        "PAT": "Net Income",
        "EPS in Rs": "Diluted EPS",
        "Earnings Per Share": "Diluted EPS",
        "Operating Profit": "Operating Income",
        "Profit Before Interest And Tax": "Operating Income",
        "Operating Income": "Operating Income",
        "EBIT": "EBIT",
        "EBITDA": "EBITDA",
        "Cost of Sales": "COGS",
        "Cost of Goods Sold": "COGS",
        "Cost of Revenue": "COGS",
        "Purchases": "COGS",
        "Gross Profit": "Gross Profit",
        "Gross Margin": "Gross Profit",
    }

    BALANCE_LABEL_RENAME = {
        "Shareholders' Equity": "Total Stockholder Equity",
        "Total Stockholders Equity": "Total Stockholder Equity",
        "Total Equity": "Total Stockholder Equity",
        "Stockholders Equity": "Total Stockholder Equity",
        "Equity": "Total Stockholder Equity",
        "Total Shareholders' Equity": "Total Stockholder Equity",
        "Total Shareholders Equity": "Total Stockholder Equity",
        "Equity Capital": "Equity Capital",
        "Reserves": "Reserves",
        "Reserves and Surplus": "Reserves",
        "Total Assets": "Total Assets",
        "Assets": "Total Assets",
        "Total Liabilities": "Total Liab",
        "Liabilities": "Total Liab",
        "Other Liabilities": "Other Liabilities",
        "Total Current Liabilities": "Total Current Liabilities",
        "Current Liabilities": "Total Current Liabilities",
        "Total Debt": "Total Debt",
        "Long Term Debt": "Long Term Debt",
        "Short Term Debt": "Short Term Debt",
        "Debt": "Total Debt",
        "Borrowings": "Borrowings",
        "Borrowing": "Borrowings",
        "Total Borrowings": "Total Debt",
        "Deposits": "Deposits",
        "Total Current Assets": "Total Current Assets",
        "Current Assets": "Total Current Assets",
        "Other Assets": "Other Assets",
        "Fixed Assets": "Fixed Assets",
        "CWIP": "CWIP",
        "Investments": "Investments",
        "Working Capital": "Working Capital",
    }

    CASHFLOW_LABEL_RENAME = {
        "Net Cash from Operating Activities": "Operating Cash Flow",
        "Cash from Operating Activities": "Operating Cash Flow",
        "Cash Flow from Operating Activities": "Operating Cash Flow",
        "Cash from Operating Activity+": "Operating Cash Flow",
        "Capital Expenditure": "Capital Expenditures",
        "Capital Expenditures": "Capital Expenditures",
        "CapEx": "Capital Expenditures",
        "Purchase of Fixed Assets": "Capital Expenditures",
        "Purchase of Property Plant and Equipment": "Capital Expenditures",
        "Net Cash from Investing Activities": "Net Cash from Investing Activities",
        "Cash Flow from Investing Activities": "Net Cash from Investing Activities",
        "Cash from Investing Activity+": "Net Cash from Investing Activities",
        "Net Cash from Financing Activities": "Net Cash from Financing Activities",
        "Cash Flow from Financing Activities": "Net Cash from Financing Activities",
        "Cash from Financing Activity+": "Net Cash from Financing Activities",
    }

    COMPANY_IR_URLS: Dict[str, str] = {
        "RELIANCE": "https://www.reliance.com/investor-relations",
        "TCS": "https://www.tcs.com/investor-relations",
        "INFY": "https://www.infosys.com/investors",
        "HDFCBANK": "https://www.hdfcbank.com/investor",
        "SBIN": "https://www.sbi.co.in/web/investor-relations",
        "ICICIBANK": "https://www.icicibank.com/investor-relations",
        "HCLTECH": "https://www.hcltech.com/investors",
        "WIPRO": "https://www.wipro.com/investors",
        "ITC": "https://www.itclimited.com/investor-relations",
        "TATAMOTORS": "https://www.tatamotors.com/investors",
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self.pdf_parser = PDFParser()
        self.xbrl_parser = XBRLParser()
        self.calculator = FinancialCalculator()
        init_db()

    def _ticker_to_slug(self, symbol: str) -> str:
        """Return the bare ticker (without exchange suffix)."""
        parts = symbol.split(".")
        return parts[0].upper()

    def _get_ir_url(self, symbol: str) -> Optional[str]:
        """Return the official investor-relations URL for a ticker.

        Only pre-registered company IR pages are used.  No third-party
        aggregators (screener.in, Yahoo, Trendlyne) are consulted.
        """
        slug = self._ticker_to_slug(symbol)
        return self.COMPANY_IR_URLS.get(slug.upper())

    def _get(self, url: str, params: dict = None) -> Optional[str]:
        if not hasattr(self, "_html_cache"):
            self._html_cache = {}
        if url in self._html_cache and self._html_cache[url]:
            return self._html_cache[url]
        try:
            resp = self.session.get(url, params=params, timeout=12)
            if resp.status_code == 200:
                self._html_cache[url] = resp.text
                return resp.text
        except Exception as e:
            logger.warning("HTTP fetch failed for %s: %s", url, e)
        return None

    def _fetch_playwright(self, url: str, wait_ms: int = 3000) -> Optional[str]:
        """Fetch a page that uses JavaScript rendering (SPAs) via Playwright.

        Falls back gracefully to requests if Playwright is unavailable.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.debug("Playwright not installed — falling back to requests for %s", url)
            return self._get(url)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_default_timeout(60000)
                page.goto(url, timeout=60000)
                time.sleep(wait_ms / 1000.0)
                content = page.content()
                browser.close()
                if content and "Access Denied" not in content[:500]:
                    return content
                logger.warning("Playwright fetch returned access denied for %s", url)
                return None
        except Exception as e:
            logger.warning("Playwright fetch failed for %s: %s", url, e)
            return None

    def _get_or_playwright(self, url: str) -> Optional[str]:
        """Try requests first; if the response looks like a JS-rendered SPA
        (very small page, no content), retry with Playwright."""
        html = self._get(url)
        if html and len(html) > 5000:
            return html
        logger.info("requests fetch for %s returned thin content — trying Playwright", url)
        return self._fetch_playwright(url)

    def _discover_pdf_links(self, html: str, base_url: str) -> List[str]:
        """Extract all PDF links from an HTML page, resolving relative URLs."""
        from urllib.parse import urljoin
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        pdfs = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().endswith(".pdf"):
                full = urljoin(base_url, href)
                pdfs.append(full)
        return pdfs

    _COMPANY_IR_PATHS: Dict[str, List[str]] = {
        "RELIANCE": [
            "https://www.relianceindustries.com/investor-relations/financial-results",
            "https://www.relianceindustries.com/investor-relations/annual-reports",
        ],
        "TCS": [
            "https://www.tcs.com/investors",
            "https://www.tcs.com/en/investors",
        ],
        "INFY": [
            "https://www.infosys.com/investors/financial-results/",
            "https://www.infosys.com/investors/listings-and-filings/quarterly-results/",
        ],
        "HDFCBANK": [
            "https://www.hdfcbank.com/investor-relations",
            "https://www.hdfcbank.com/investor-relations/financial-results",
        ],
        "SBIN": [
            "https://sbi.bank.in/web/investor-relations/reports",
            "https://www.sbi.co.in/web/investor-relations",
        ],
        "ICICIBANK": [
            "https://www.icicibank.com/investor-relations",
            "https://www.icicibank.com/investor-relations/financial-results",
        ],
        "HCLTECH": [
            "https://www.hcltech.com/investors",
        ],
        "WIPRO": [
            "https://www.wipro.com/investors/",
        ],
        "ITC": [
            "https://www.itclimited.com/investor-relations",
        ],
        "TATAMOTORS": [
            "https://www.tatamotors.com/investors",
        ],
    }

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
            }

            # Attach cached shareholding data if present
            if any(cached.get(k) is not None for k in ("promoter_pct", "fii_pct", "dii_pct",
                                                        "govt_pct", "public_pct", "institutional_pct",
                                                        "shareholders_count")):
                import json as _json
                sh_json = cached.get("shareholding_json")
                sh_table = None
                history = None
                if sh_json:
                    try:
                        sh_table = pd.DataFrame(_json.loads(sh_json))
                        if sh_table is not None and not sh_table.empty and sh_table.shape[1] >= 2:
                            hist_cols = [str(c) for c in sh_table.columns[1:]]
                            history = {"periods": hist_cols}
                            category_map = {
                                "Promoters": "Promoter_Pct",
                                "FIIs": "FII_Pct",
                                "DIIs": "DII_Pct",
                                "Government": "Govt_Pct",
                                "Public": "Public_Pct",
                            }
                            for _, row in sh_table.iterrows():
                                label_clean = re.sub(r'[^a-zA-Z]', '', str(row.iloc[0])).lower()
                                for display_name in category_map:
                                    if display_name.lower() in label_clean:
                                        vals = []
                                        for col in sh_table.columns[1:]:
                                            v_str = str(row[col]).replace("%", "").strip()
                                            try:
                                                vals.append(float(v_str))
                                            except (ValueError, TypeError):
                                                vals.append(None)
                                        history[display_name] = vals
                                        break
                    except Exception:
                        pass
                result.update({
                    "Promoter_Pct": cached.get("promoter_pct"),
                    "FII_Pct": cached.get("fii_pct"),
                    "DII_Pct": cached.get("dii_pct"),
                    "Govt_Pct": cached.get("govt_pct"),
                    "Public_Pct": cached.get("public_pct"),
                    "Institutional_Pct": cached.get("institutional_pct"),
                    "Shareholders_Count": cached.get("shareholders_count"),
                    "Shareholding_Period": cached.get("shareholding_period"),
                    "Shareholding_Table": sh_table,
                    "Shareholding_History": history,
                })
            return result

        slug = self._ticker_to_slug(symbol)
        ir_url = self._get_ir_url(slug)
        if not ir_url:
            logger.warning("No official IR URL registered for %s", slug)
            return {}

        html = self._get_or_playwright(ir_url)
        if not html:
            return {}

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        company_name = self._extract_company_name(soup)
        sector = self._extract_sector(soup)
        industry = self._extract_industry(soup)
        market_cap = self._extract_market_cap(soup)
        shares_outstanding = self._extract_shares_outstanding(soup)

        info = {
            "ticker": symbol,
            "company_name": company_name,
            "sector": sector,
            "industry": industry,
            "market_cap": market_cap,
            "sharesOutstanding": shares_outstanding,
        }

        # Extract and persist shareholding data alongside company info
        sh_info = self._extract_shareholding(soup)
        if sh_info and any(sh_info.get(k) is not None for k in ("Promoter_Pct", "FII_Pct", "DII_Pct",
                                                                   "Govt_Pct", "Public_Pct", "Institutional_Pct")):
            import json as _json
            sh_json = None
            if sh_info.get("Shareholding_Table") is not None:
                try:
                    sh_json = _json.dumps(sh_info["Shareholding_Table"].to_dict(), default=str)
                except Exception:
                    sh_json = None

            save_company_info({
                "ticker": symbol,
                "company_name": company_name,
                "sector": sector,
                "industry": industry,
                "market_cap": market_cap,
                "shares_outstanding": shares_outstanding,
                "promoter_pct": sh_info.get("Promoter_Pct"),
                "fii_pct": sh_info.get("FII_Pct"),
                "dii_pct": sh_info.get("DII_Pct"),
                "govt_pct": sh_info.get("Govt_Pct"),
                "public_pct": sh_info.get("Public_Pct"),
                "institutional_pct": sh_info.get("Institutional_Pct"),
                "shareholders_count": sh_info.get("Shareholders_Count"),
                "shareholding_json": sh_json,
                "shareholding_period": sh_info.get("Shareholding_Period"),
            })
        else:
            save_company_info({
                "ticker": symbol,
                "company_name": company_name,
                "sector": sector,
                "industry": industry,
                "market_cap": market_cap,
                "shares_outstanding": shares_outstanding,
            })

        # Merge shareholding into info returned to caller
        info.update({
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
        })

        return info

    def _extract_company_name(self, soup) -> Optional[str]:
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
        return None

    def _extract_sector(self, soup) -> Optional[str]:
        peer_sec = soup.find("section", id="peers")
        if peer_sec:
            links = peer_sec.find_all("a", href=lambda h: h and "/market/" in h)
            link_texts = [a.get_text(strip=True) for a in links]
            if len(link_texts) >= 1:
                return link_texts[0]
        for p in soup.find_all(["p", "span"]):
            text = p.get_text(strip=True)
            if "Sector" in text:
                parts = text.split(":")
                if len(parts) > 1:
                    return parts[1].strip()
        return None

    def _extract_industry(self, soup) -> Optional[str]:
        peer_sec = soup.find("section", id="peers")
        if peer_sec:
            links = peer_sec.find_all("a", href=lambda h: h and "/market/" in h)
            link_texts = [a.get_text(strip=True) for a in links]
            if len(link_texts) >= 2:
                return link_texts[-1]
        for p in soup.find_all(["p", "span"]):
            text = p.get_text(strip=True)
            if "Industry" in text:
                parts = text.split(":")
                if len(parts) > 1:
                    return parts[1].strip()
        return None

    def _extract_market_cap(self, soup) -> Optional[float]:
        for li in soup.find_all(["li", "p", "div"]):
            txt = li.get_text(separator=" ", strip=True)
            if "Market Cap" in txt:
                val = self._parse_number(txt.replace("Market Cap", "").strip())
                if val is not None and val > 0:
                    return val
        return None

    def _extract_shares_outstanding(self, soup) -> Optional[float]:
        for li in soup.find_all(["li", "p", "div"]):
            txt = li.get_text(separator=" ", strip=True)
            if "Shares" in txt and "Outstanding" in txt:
                val = self._parse_number(txt.replace("Shares", "").replace("Outstanding", "").strip())
                if val is not None and val > 0:
                    return val
        return None

    def _extract_shareholding(self, soup) -> Dict[str, Any]:
        tables = soup.find_all("table")
        sh_dict = {}
        for table in tables:
            txt = table.get_text()
            if "Promoter" in txt or "FII" in txt or "DII" in txt or "Shareholding" in txt:
                try:
                    from io import StringIO
                    dfs = pd.read_html(StringIO(str(table)))
                    if dfs and not dfs[0].empty:
                        df = dfs[0]
                        row_map = {}
                        for _, row in df.iterrows():
                            label_raw = str(row.iloc[0])
                            label_clean = re.sub(r'[^a-zA-Z]', '', label_raw).lower()
                            latest_val = None
                            for val_col in reversed(row.iloc[1:]):
                                v_str = re.sub(r'[^0-9.]', '', str(val_col))
                                if v_str:
                                    try:
                                        latest_val = float(v_str)
                                        break
                                    except Exception:
                                        pass
                            if label_clean and latest_val is not None:
                                row_map[label_clean] = latest_val

                        prom = row_map.get("promoter") or row_map.get("promoters") or row_map.get("promoterpromotergroup")
                        fii = row_map.get("fii") or row_map.get("fiis") or row_map.get("fpi") or row_map.get("fpis")
                        dii = row_map.get("dii") or row_map.get("diis") or row_map.get("domesticinstitutionalinvestors")
                        govt = row_map.get("govt") or row_map.get("government")
                        pub = row_map.get("public") or row_map.get("retail")
                        sh_count = row_map.get("noofshareholders") or row_map.get("shareholders")

                        if prom is not None or fii is not None or dii is not None:
                            inst = round((fii or 0.0) + (dii or 0.0), 2)
                            # Get the period label from the DataFrame columns (skip first col if it's unnamed/index)
                            period_label = None
                            if len(df.columns) > 1:
                                col_labels = [str(c) for c in df.columns[1:]]
                                period_label = col_labels[-1] if col_labels else None

                            # Build historical time-series for chart plotting
                            history = {"periods": [str(c) for c in df.columns[1:]] if len(df.columns) > 1 else []}
                            category_map = {
                                "Promoters": "Promoter_Pct",
                                "FIIs": "FII_Pct",
                                "DIIs": "DII_Pct",
                                "Government": "Govt_Pct",
                                "Public": "Public_Pct",
                            }
                            for _, hist_row in df.iterrows():
                                hist_label = re.sub(r'[^a-zA-Z]', '', str(hist_row.iloc[0])).lower()
                                for display_name, dict_key in category_map.items():
                                    if display_name.lower() in hist_label:
                                        vals = []
                                        for col in df.columns[1:]:
                                            v_str = re.sub(r'[^0-9.]', '', str(hist_row[col]))
                                            try:
                                                vals.append(float(v_str))
                                            except (ValueError, TypeError):
                                                vals.append(None)
                                        history[display_name] = vals
                                        break

                            return {
                                "Promoter_Pct": prom,
                                "FII_Pct": fii,
                                "DII_Pct": dii,
                                "Govt_Pct": govt,
                                "Public_Pct": pub,
                                "Institutional_Pct": inst,
                                "Shareholders_Count": sh_count,
                                "Shareholding_Period": period_label,
                                "Shareholding_Table": df,
                                "Shareholding_History": history,
                            }
                except Exception:
                    continue
        return sh_dict

    @staticmethod
    def _parse_number(text: str) -> Optional[float]:
        if not text:
            return None
        text = text.replace(",", "").replace("\u20b9", "").replace("$", "").strip()
        multipliers = {"Cr": 1e7, "Lakh": 1e5, "M": 1e6, "B": 1e9, "T": 1e12}
        for mult, val in multipliers.items():
            if mult in text:
                try:
                    return float(text.replace(mult, "").strip()) * val
                except Exception:
                    return None
        try:
            return float(text)
        except Exception:
            return None

    def ingest_report(self, symbol: str, source: str, period: str, report_date: str, financial_year: int, quarter: Optional[int] = None):
        fmt = self.infer_format(source)
        if fmt == "pdf":
            raw = self.pdf_parser.parse_file(source)
            if not raw:
                raw = self.pdf_parser.parse_bytes(self._download_bytes(source), source)
        elif fmt == "xbrl":
            raw = self.xbrl_parser.parse_file(source)
            if not raw:
                raw = self.xbrl_parser.parse_bytes(self._download_bytes(source), source)
        elif fmt in ("html", "url"):
            raw = self._ingest_html(source)
        else:
            raw = {}

        if raw:
            self._store_record(symbol, period, report_date, financial_year, quarter, raw)
        return raw

    def _download_bytes(self, url: str) -> bytes:
        try:
            resp = self.session.get(url, timeout=30)
            if resp.status_code == 200:
                return resp.content
        except Exception:
            pass
        return b""

    def _ingest_html(self, source: str) -> Dict[str, Any]:
        if self.is_url(source):
            html = self._get(source)
        else:
            try:
                with open(source, "r", encoding="utf-8") as f:
                    html = f.read()
            except Exception:
                return {}

        if not html:
            return {}

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        result = {}
        for table in tables:
            df = self._table_to_dataframe(table)
            if df is None or df.empty:
                continue
            income = self._normalize_labels(df, self.INCOME_LABEL_RENAME)
            for canonical in ["Total Revenue", "Operating Income", "EBIT", "EBITDA",
                              "Net Income", "Gross Profit"]:
                val = _find_in_normalized(income, canonical)
                if val is not None and result.get(_canonical_to_key(canonical)) is None:
                    result[_canonical_to_key(canonical)] = val
            balance = self._normalize_labels(df, self.BALANCE_LABEL_RENAME)
            for canonical in ["Total Assets", "Total Liab", "Total Debt",
                              "Equity Capital", "Reserves", "Borrowings"]:
                val = _find_in_normalized(balance, canonical)
                if val is not None and result.get(_canonical_bs_to_key(canonical)) is None:
                    result[_canonical_bs_to_key(canonical)] = val
        return result

    def _extract_latest_value(self, df: pd.DataFrame, metric: str, col=None) -> Optional[float]:
        """Search a (possibly normalized) DataFrame for a metric by canonical label.

        If col is provided, read from that column; otherwise use the first column.
        """
        canonical_map = {
            "revenue":           ["Total Revenue", "Revenue", "Sales", "Sales+"],
            "operating_profit":  ["Operating Income", "Operating Profit", "Financing Profit",
                                  "PBIDT"],
            "ebit":              ["EBIT", "EBITDA", "Operating Income"],
            "pat":               ["Net Income", "PAT", "Profit After Tax", "Net Profit", "Net Profit+"],
            "eps":               ["Diluted EPS", "Basic EPS", "EPS", "Earnings Per Share", "EPS in Rs"],
            "depreciation_amortization": ["Depreciation", "Depreciation And Amortization",
                                          "Depreciation, Depletion & Amortisation"],
            "equity":            ["Total Stockholder Equity", "Equity Capital", "Reserves",
                                  "Total Equity", "Equity"],
            "current_assets":    ["Total Current Assets", "Current Assets"],
            "cash_and_cash_equivalents": ["CashAndCashEquivalents", "Cash & Cash Equivalents",
                                          "Cash and Cash Equivalents", "Cash",
                                          "Cash in Hand", "Balance with RBI", "Cash with RBI",
                                          "Balances with RBI"],
            "assets":            ["Total Assets", "Assets"],
            "liabilities":       ["Total Liab", "Total Liabilities", "Liabilities", "Other Liabilities",
                                  "Deposits"],
            "current_liabilities": ["Total Current Liabilities", "Current Liabilities"],
            "working_capital":   ["Working Capital"],
            "debt":              ["Total Debt", "Borrowings", "Borrowing", "Total Borrowings", "Debt"],
            "operating_cash_flow": ["Operating Cash Flow", "Cash from Operating Activity+",
                                     "Cash Flow from Operating Activities",
                                     "Net Cash from Operating Activities"],
            "capex":             ["Capital Expenditures", "Capital Expenditure",
                                  "Purchase of Fixed Assets", "Free Cash Flow",
                                  "Purchase of Property Plant and Equipment"],
            "gross_profit":      ["Gross Profit", "Gross Sales"],
            "retained_earnings": ["Reserves", "Retained Earnings", "Reserves and Surplus"],
        }
        candidates = canonical_map.get(metric, [])
        if not candidates:
            return None

        if df is None or df.empty:
            return None

        df_norm = self._normalize_labels(df.copy(), self.INCOME_LABEL_RENAME)
        df_norm = self._normalize_labels(df_norm, self.BALANCE_LABEL_RENAME)
        df_norm = self._normalize_labels(df_norm, self.CASHFLOW_LABEL_RENAME)
        df_idx = [str(i) for i in df_norm.index]

        for candidate in candidates:
            for idx_label in df_idx:
                if candidate.lower() in idx_label.lower():
                    try:
                        target_col = col if col in df_norm.columns else df_norm.columns[0]
                        val = df_norm.loc[idx_label, target_col]
                        return FinancialCalculator._safe(val)
                    except Exception:
                        continue
        return None

    def _store_record(self, symbol: str, period: str, report_date: str, financial_year: int, quarter: Optional[int], raw: Dict[str, Any]):
        record = {
            "ticker": symbol,
            "company": None,
            "report_date": report_date,
            "period": period,
            "quarter": quarter,
            "financial_year": financial_year,
            "revenue": raw.get("revenue"),
            "operating_profit": raw.get("operating_profit"),
            "ebit": raw.get("ebit"),
            "pat": raw.get("pat"),
            "eps": raw.get("eps"),
            "equity": raw.get("equity"),
            "assets": raw.get("total_assets"),
            "liabilities": raw.get("total_liabilities"),
            "current_liabilities": raw.get("current_liabilities"),
            "debt": raw.get("total_debt"),
            "operating_cash_flow": raw.get("operating_cash_flow"),
            "capex": raw.get("capex"),
            "source": "company_ir",
            "source_type": "company_ir",
            "verification_status": "verified",
        }
        save_fundamental_report(record)

    def _fetch_screener_tables(self, symbol: str):
        slug = self._ticker_to_slug(symbol)
        ir_url = self._get_ir_url(slug)
        if not ir_url:
            return None, None, None, None
        html = self._get_or_playwright(ir_url)
        if not html:
            return None, None, None, None

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")

        quarterly_income = None
        annual_income = None
        balance_sheet = None
        cashflow = None

        income_candidates = []

        for table in tables:
            header_text = self._get_table_header_text(table)
            if not header_text:
                continue

            df = self._table_to_dataframe(table)
            if df is None or df.empty:
                continue

            index_labels = [str(idx).lower().strip() for idx in df.index]

            if balance_sheet is None and self._looks_like_balance_sheet(index_labels):
                balance_sheet = df
                continue

            if cashflow is None and self._looks_like_cashflow(index_labels):
                cashflow = df
                continue

            if self._looks_like_quarterly_income(df, index_labels) or self._looks_like_annual_income(df, index_labels):
                is_annual_style = self._has_fy_columns(df)
                is_quarterly_style = self._has_quarter_columns(df)
                income_candidates.append((df, is_annual_style, is_quarterly_style))

        if len(income_candidates) >= 1:
            annual_candidates = [c for c in income_candidates if c[1]]
            quarterly_candidates = [c for c in income_candidates if c[2]]

            if annual_candidates:
                annual_income = annual_candidates[0][0]
            elif len(income_candidates) == 1:
                annual_income = income_candidates[0][0]

            if quarterly_candidates:
                quarterly_income = quarterly_candidates[0][0]
            elif len(income_candidates) == 1 and not annual_candidates[0][1]:
                quarterly_income = income_candidates[0][0]

        return quarterly_income, annual_income, balance_sheet, cashflow

    def _ingest_from_ir_pages(self, symbol: str) -> bool:
        """Discover, download, and parse the latest official quarterly report
        from the company's investor-relations website.

        Uses Playwright for JS-heavy SPAs and requests as a fallback.
        Returns True if any data was successfully stored.
        """
        slug = self._ticker_to_slug(symbol)
        ir_paths = self._COMPANY_IR_PATHS.get(slug.upper(), [])
        if not ir_paths:
            return False

        found_html = None
        pdf_links: List[str] = []
        for url in ir_paths:
            if not found_html:
                html = self._get_or_playwright(url)
                if html and "Access Denied" not in html[:500]:
                    found_html = html
            # Collect PDF links from all IR pages
            html = self._get_or_playwright(url)
            if html:
                pdfs = self._discover_pdf_links(html, url)
                pdf_links.extend(pdfs)

        if found_html and not pdf_links:
            # Try to extract tables directly from the IR page HTML
            tables = self._extract_tables_from_html(found_html, symbol)
            if tables:
                self._store_table_data(symbol, tables, found_html, ir_paths[0])
                return True

        # Download and parse PDFs
        for pdf_url in pdf_links[:10]:
            if not pdf_url.lower().endswith(".pdf"):
                continue
            try:
                resp = self.session.get(pdf_url, timeout=30)
                if resp.status_code == 200:
                    pdf_bytes = resp.content
                    parsed = self._parse_pdf_bytes(pdf_bytes, pdf_url, symbol)
                    if parsed:
                        self._store_table_data(symbol, parsed, pdf_url, pdf_url)
                        return True
            except Exception as e:
                logger.warning("Failed to download/parse PDF %s: %s", pdf_url, e)

        return False

    def _extract_tables_from_html(self, html: str, symbol: str) -> Optional[Dict[str, Any]]:
        """Extract financial tables from HTML IR page content."""
        from bs4 import BeautifulSoup
        from io import StringIO
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            return None
        result = {}
        for table in tables:
            try:
                df = pd.read_html(StringIO(str(table)))[0]
                if df.empty or len(df.columns) < 2:
                    continue
                df = df.set_index(df.columns[0])
                index_labels = [str(idx).lower().strip() for idx in df.index]
                metrics = self._extract_metrics(df, symbol)
                if metrics:
                    for k, v in metrics.items():
                        if v is not None:
                            result[k] = v
            except Exception:
                continue
        return result if result else None

    def _extract_metrics(self, df: pd.DataFrame, symbol: str) -> Dict[str, Optional[float]]:
        """Extract key metrics from a normalized DataFrame."""
        metrics = {}
        for col in df.columns:
            col_str = str(col)
            for metric_name, labels in [
                ("revenue", ["Total Revenue", "Revenue", "Sales", "Operating Revenue"]),
                ("pat", ["Net Income", "PAT", "Net Profit", "Profit After Tax"]),
                ("ebit", ["EBIT", "EBITDA", "Operating Income", "Operating Profit"]),
                ("equity", ["Total Stockholder Equity", "Total Equity"]),
                ("assets", ["Total Assets"]),
                ("debt", ["Total Debt", "Borrowings"]),
            ]:
                val = self._extract_latest_value(df, metric_name, col)
                if val is not None:
                    metrics[metric_name] = val
        return metrics

    def _parse_pdf_bytes(self, pdf_bytes: bytes, source_url: str, symbol: str) -> Optional[Dict[str, Any]]:
        """Parse a PDF's financial tables and extract metrics."""
        try:
            tables = self.pdf_parser.extract_tables_from_bytes(pdf_bytes)
            if not tables:
                return None
            result = {}
            for df in tables:
                if df is None or df.empty or len(df.columns) < 2:
                    continue
                df = df.set_index(df.columns[0])
                index_labels = [str(idx).lower().strip() for idx in df.index]
                metrics = self._extract_metrics(df, symbol)
                if metrics:
                    for k, v in metrics.items():
                        if v is not None:
                            result[k] = v
            return result if result else None
        except Exception as e:
            logger.warning("PDF parse failed for %s: %s", source_url, e)
            return None

    def _store_table_data(self, symbol: str, tables: Dict[str, Any], source_url: str, report_date: str):
        """Store extracted table data as a quarterly report record."""
        from datetime import datetime as dt
        today = dt.now().strftime("%Y-%m-%d")
        record = {
            "ticker": symbol,
            "company": None,
            "report_date": today,
            "period": "quarterly",
            "quarter": None,
            "financial_year": None,
            "revenue": tables.get("revenue"),
            "operating_profit": tables.get("ebit"),
            "ebit": tables.get("ebit"),
            "pat": tables.get("pat"),
            "eps": tables.get("eps"),
            "equity": tables.get("equity"),
            "assets": tables.get("assets"),
            "debt": tables.get("debt"),
            "source": "company_ir",
            "source_type": "company_ir",
            "source_url": source_url,
            "verification_status": "verified",
        }
        save_fundamental_report(record)

    @staticmethod
    def _has_fy_columns(df: pd.DataFrame) -> bool:
        cols = [str(c).strip() for c in df.columns]
        fy_pattern = re.compile(r'^(FY)?\d{2,4}$', re.IGNORECASE)
        mar_pattern = re.compile(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}$', re.IGNORECASE)
        ttm_count = sum(1 for c in cols if c.upper() == 'TTM')
        fy_count = sum(1 for c in cols if fy_pattern.match(c))
        mar_count = sum(1 for c in cols if mar_pattern.match(c))
        if ttm_count > 0 and mar_count >= 3:
            return True
        if fy_count >= 5:
            return True
        return False

    @staticmethod
    def _has_quarter_columns(df: pd.DataFrame) -> bool:
        cols = [str(c).strip() for c in df.columns]
        mon_pattern = re.compile(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}$', re.IGNORECASE)
        mon_count = sum(1 for c in cols if mon_pattern.match(c))
        if mon_count < 3:
            return False
        months = set()
        for c in cols:
            m = mon_pattern.match(c)
            if m:
                month_str = m.group(1).lower()[:3]
                months.add(month_str)
        quarter_months = {"mar", "jun", "sep", "dec"}
        return len(months.intersection(quarter_months)) >= 2

    def _get_table_header_text(self, table) -> str:
        header = table.find("thead")
        if header:
            return header.get_text(separator=" ", strip=True).lower()
        first_row = table.find("tr")
        if first_row:
            return first_row.get_text(separator=" ", strip=True).lower()
        return ""

    @staticmethod
    def _looks_like_quarterly_income(df, index_labels) -> bool:
        quarterly_markers = ["sales+", "revenue+", "operating profit", "net profit+",
                             "eps in rs", "other income+", "financing profit"]
        has_marker = any(m in index_labels for m in quarterly_markers)
        # Banks often have 4 columns (quarterly), non-banks 8+
        has_cols = len(df.columns) >= 4
        return has_marker and has_cols

    @staticmethod
    def _looks_like_annual_income(df, index_labels) -> bool:
        annual_markers = ["sales+", "revenue+", "operating profit", "net profit+",
                          "eps in rs", "financing profit"]
        has_marker = any(m in index_labels for m in annual_markers)
        has_rows = len(df) >= 6
        return has_marker and has_rows

    @staticmethod
    def _looks_like_balance_sheet(index_labels) -> bool:
        bs_markers = ["equity capital", "reserves", "borrowings+", "borrowing",
                       "total liabilities", "total assets", "deposits"]
        return any(m in index_labels for m in bs_markers)

    @staticmethod
    def _looks_like_cashflow(index_labels) -> bool:
        cf_markers = ["cash from operating activity+", "free cash flow",
                       "cash from investing activity+"]
        return any(m in index_labels for m in cf_markers)

    def _table_to_dataframe(self, table) -> Optional[pd.DataFrame]:
        try:
            from io import StringIO
            html_str = str(table)
            dfs = pd.read_html(StringIO(html_str))
            if not dfs:
                return None
            df = dfs[0]
            if df.empty or len(df.columns) < 2:
                return None
            df = df.set_index(df.columns[0])
            return df
        except Exception:
            return None

    def _is_quarterly_table(self, header_text: str, df: pd.DataFrame) -> bool:
        if "quarterly" in header_text or "quarter" in header_text:
            return True
        cols = [str(c) for c in df.columns]
        for c in cols:
            if re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}', c, re.IGNORECASE):
                return True
        return False

    def _is_annual_table(self, header_text: str, df: pd.DataFrame) -> bool:
        if "annual" in header_text or "year" in header_text:
            return True
        cols = [str(c) for c in df.columns]
        for c in cols:
            if re.match(r'^(fy)?\d{2,4}$', c.strip(), re.IGNORECASE):
                return True
        return False

    def _is_balance_sheet_table(self, header_text: str, df: pd.DataFrame) -> bool:
        if "balance" in header_text or "balance sheet" in header_text:
            return True
        for idx in df.index:
            if "equity" in str(idx).lower() and "asset" in str(idx).lower():
                return True
        return False

    def _is_cashflow_table(self, header_text: str, df: pd.DataFrame) -> bool:
        if "cash flow" in header_text or "cashflow" in header_text:
            return True
        for idx in df.index:
            if "cash" in str(idx).lower() and ("operating" in str(idx).lower() or "investing" in str(idx).lower()):
                return True
        return False

    def _normalize_periods(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        new_cols = []
        for c in df.columns:
            nc = _ReportHelpers.normalize_period(str(c))
            new_cols.append(nc if nc else str(c))
        df = df.copy()
        df.columns = new_cols
        df = df.loc[:, ~df.columns.duplicated()]
        return df

    def _normalize_labels(self, df: pd.DataFrame, rename_map: dict) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        new_index = []
        for idx in df.index:
            s = str(idx)
            if s in rename_map:
                new_index.append(rename_map[s])
            else:
                matched = False
                for key, val in rename_map.items():
                    if key.lower() in s.lower():
                        new_index.append(val)
                        matched = True
                        break
                if not matched:
                    new_index.append(s)
        df = df.copy()
        df.index = new_index
        return df

    def get_quarterly_financials(self, symbol: str) -> Optional[pd.DataFrame]:
        q_income, _, _, _ = self._fetch_screener_tables(symbol)
        if q_income is None or q_income.empty:
            return None
        q_income = self._normalize_periods(q_income)
        q_income = self._normalize_labels(q_income, self.INCOME_LABEL_RENAME)
        if q_income.empty:
            return None
        self._store_quarterly_data(symbol, q_income)
        return q_income

    def get_annual_financials(self, symbol: str) -> Optional[pd.DataFrame]:
        _, annual_income, _, _ = self._fetch_screener_tables(symbol)
        if annual_income is None or annual_income.empty:
            return None
        annual_income = self._normalize_periods(annual_income)
        annual_income = self._normalize_labels(annual_income, self.INCOME_LABEL_RENAME)
        if annual_income.empty:
            return None
        self._store_annual_data(symbol, annual_income)
        return annual_income

    def get_quarterly_balance_sheet(self, symbol: str) -> Optional[pd.DataFrame]:
        _, _, balance_sheet, _ = self._fetch_screener_tables(symbol)
        if balance_sheet is None or balance_sheet.empty:
            return None
        balance_sheet = self._normalize_periods(balance_sheet)
        balance_sheet = self._normalize_labels(balance_sheet, self.BALANCE_LABEL_RENAME)
        return balance_sheet

    def get_annual_balance_sheet(self, symbol: str) -> Optional[pd.DataFrame]:
        _, _, balance_sheet, _ = self._fetch_screener_tables(symbol)
        if balance_sheet is None or balance_sheet.empty:
            return None
        balance_sheet = self._normalize_periods(balance_sheet)
        balance_sheet = self._normalize_labels(balance_sheet, self.BALANCE_LABEL_RENAME)
        return balance_sheet

    def get_quarterly_cashflow(self, symbol: str) -> Optional[pd.DataFrame]:
        _, _, _, cashflow = self._fetch_screener_tables(symbol)
        if cashflow is None or cashflow.empty:
            return None
        cashflow = self._normalize_periods(cashflow)
        cashflow = self._normalize_labels(cashflow, self.CASHFLOW_LABEL_RENAME)
        return cashflow

    def get_annual_cashflow(self, symbol: str) -> Optional[pd.DataFrame]:
        _, _, _, cashflow = self._fetch_screener_tables(symbol)
        if cashflow is None or cashflow.empty:
            return None
        cashflow = self._normalize_periods(cashflow)
        cashflow = self._normalize_labels(cashflow, self.CASHFLOW_LABEL_RENAME)
        return cashflow

    def get_source(self) -> str:
        return "company_ir"

    def _ensure_ir_data(self, symbol: str):
        """Ensure company IR data is available in the DB.

        Tries the standard IR page tables first, then falls back to
        Playwright-based SPA scraping and PDF parsing.
        """
        q_df = get_latest_quarterly_reports(symbol, limit=1)
        if q_df.empty:
            self._ingest_from_ir_pages(symbol)

    def _store_quarterly_data(self, symbol: str, q_income: pd.DataFrame):
        if q_income is None or q_income.empty:
            return

        _, _, balance_sheet, cashflow = self._fetch_screener_tables(symbol)

        for col in q_income.columns:
            period_str = _ReportHelpers.normalize_period(col)
            if not period_str:
                continue

            quarter = _ReportHelpers.derive_quarter(col)
            financial_year = _ReportHelpers.derive_financial_year(col, quarter)

            record = {
                "ticker": symbol,
                "company": None,
                "report_date": period_str,
                "period": "quarterly",
                "quarter": quarter,
                "financial_year": financial_year,
                "revenue": self._extract_latest_value(q_income, "revenue", col),
                "operating_profit": self._extract_latest_value(q_income, "operating_profit", col),
                "ebit": self._extract_latest_value(q_income, "ebit", col),
                "pat": self._extract_latest_value(q_income, "pat", col),
                "eps": self._extract_latest_value(q_income, "eps", col),
                "equity": _sum_balance(balance_sheet, ["Equity Capital", "Reserves", "Total Stockholder Equity"]) if balance_sheet is not None else None,
                "assets": _extract_balance(balance_sheet, "Total Assets") if balance_sheet is not None else None,
                "liabilities": _extract_balance(balance_sheet, "Total Liab") if balance_sheet is not None else None,
                "current_assets": _extract_balance(balance_sheet, "Total Current Assets") if balance_sheet is not None else None,
                "current_liabilities": _extract_balance(balance_sheet, "Total Current Liabilities") if balance_sheet is not None else None,
                "cash_and_cash_equivalents": _extract_balance(balance_sheet, "CashAndCashEquivalents") if balance_sheet is not None else None,
                "working_capital": None,
                "debt": _extract_balance(balance_sheet, "Total Debt") or _extract_balance(balance_sheet, "Borrowings") if balance_sheet is not None else None,
                "total_debt": _extract_balance(balance_sheet, "Total Debt") or _extract_balance(balance_sheet, "Borrowings") if balance_sheet is not None else None,
                "share_capital": _extract_balance(balance_sheet, "Equity Capital") if balance_sheet is not None else None,
                "face_value": self._lookup_face_value(symbol),
                "operating_cash_flow": _extract_cf(cashflow, "Operating Cash Flow") if cashflow is not None else None,
                "capex": _extract_cf(cashflow, "Capital Expenditures") if cashflow is not None else None,
                "depreciation_amortization": self._extract_latest_value(q_income, "depreciation_amortization", col),
                "source": "company_ir",
            }

            ca = record.get("current_assets")
            cl = record.get("current_liabilities")
            if ca is not None and cl is not None:
                record["working_capital"] = ca - cl

            save_fundamental_report(record)

        quarterly_reports = get_latest_quarterly_reports(symbol, n=8)
        if not quarterly_reports.empty:
            reports = quarterly_reports.to_dict("records")
            ttm = self.calculator.compute_ttm(reports)
            if ttm:
                ttm["ticker"] = symbol
                ttm["period"] = "ttm"
                if reports:
                    first_date = reports[0].get("report_date")
                    if first_date:
                        q0 = _ReportHelpers.derive_quarter(first_date)
                        ttm["financial_year"] = _ReportHelpers.derive_financial_year(first_date, q0)
                save_ttm_record(ttm)

    def _store_annual_data(self, symbol: str, annual_income: pd.DataFrame):
        if annual_income is None or annual_income.empty:
            return

        _, _, balance_sheet, cashflow = self._fetch_screener_tables(symbol)

        for col in annual_income.columns:
            period_str = _ReportHelpers.normalize_period(col)
            if not period_str:
                continue

            financial_year = _ReportHelpers.derive_annual_financial_year(col)
            if financial_year is None:
                continue

            record = {
                "ticker": symbol,
                "company": None,
                "report_date": period_str,
                "period": "annual",
                "quarter": None,
                "financial_year": financial_year,
                "revenue": self._extract_latest_value(annual_income, "revenue", col),
                "operating_profit": self._extract_latest_value(annual_income, "operating_profit", col),
                "ebit": self._extract_latest_value(annual_income, "ebit", col),
                "pat": self._extract_latest_value(annual_income, "pat", col),
                "eps": self._extract_latest_value(annual_income, "eps", col),
                "equity": _sum_balance(balance_sheet, ["Equity Capital", "Reserves", "Total Stockholder Equity"]) if balance_sheet is not None else None,
                "assets": _extract_balance(balance_sheet, "Total Assets") if balance_sheet is not None else None,
                "liabilities": _extract_balance(balance_sheet, "Total Liab") if balance_sheet is not None else None,
                "current_assets": _extract_balance(balance_sheet, "Total Current Assets") if balance_sheet is not None else None,
                "current_liabilities": _extract_balance(balance_sheet, "Total Current Liabilities") if balance_sheet is not None else None,
                "cash_and_cash_equivalents": _extract_balance(balance_sheet, "CashAndCashEquivalents") if balance_sheet is not None else None,
                "working_capital": None,
                "debt": _extract_balance(balance_sheet, "Total Debt") or _extract_balance(balance_sheet, "Borrowings") if balance_sheet is not None else None,
                "total_debt": _extract_balance(balance_sheet, "Total Debt") or _extract_balance(balance_sheet, "Borrowings") if balance_sheet is not None else None,
                "share_capital": _extract_balance(balance_sheet, "Equity Capital") if balance_sheet is not None else None,
                "face_value": self._lookup_face_value(symbol),
                "operating_cash_flow": _extract_cf(cashflow, "Operating Cash Flow") if cashflow is not None else None,
                "capex": _extract_cf(cashflow, "Capital Expenditures") if cashflow is not None else None,
                "depreciation_amortization": self._extract_latest_value(annual_income, "depreciation_amortization", col),
                "source": "company_ir",
            }

            ca = record.get("current_assets")
            cl = record.get("current_liabilities")
            if ca is not None and cl is not None:
                record["working_capital"] = ca - cl

            save_fundamental_report(record)

    def _lookup_face_value(self, symbol: str) -> Optional[float]:
        """Look up face value from the database (populated by NSE XBRL filings).

        Returns None when no NSE XBRL face value is on record so that callers
        never fall back to a hard-coded default.
        """
        try:
            from data.database import get_latest_annual_reports, get_latest_quarterly_reports
            for df in (get_latest_annual_reports(symbol, limit=1), get_latest_quarterly_reports(symbol, limit=1)):
                if not df.empty and "face_value" in df.columns:
                    fv = df.iloc[0].get("face_value")
                    if fv is not None:
                        try:
                            fv_f = float(fv)
                            if fv_f > 0:
                                return fv_f
                        except (ValueError, TypeError):
                            pass
        except Exception:
            pass
        return None

    def build_fundamentals_dict(self, symbol: str) -> Dict[str, Any]:
        # Ensure we have data from company IR pages (Playwright-based discovery)
        self._ensure_ir_data(symbol)

        info = self.get_company_info(symbol)
        q_fin = self.get_quarterly_financials(symbol)
        q_balance = self.get_quarterly_balance_sheet(symbol)
        annual_income = self.get_annual_financials(symbol)
        annual_balance = self.get_annual_balance_sheet(symbol)
        annual_cashflow = self.get_annual_cashflow(symbol)

        quarterly_reports = get_latest_quarterly_reports(symbol, n=8)
        annual_reports = get_latest_annual_reports(symbol, n=5)
        ttm_record = get_ttm_record(symbol, "ttm")

        latest_quarterly = None
        if not quarterly_reports.empty:
            latest_quarterly = quarterly_reports.iloc[0].to_dict()

        latest_annual = None
        if not annual_reports.empty:
            latest_annual = annual_reports.iloc[0].to_dict()

        ratios_q = {}
        if latest_quarterly:
            ratios_q = self.calculator.compute_all_ratios(latest_quarterly)

        ratios_a = {}
        if latest_annual:
            ratios_a = self.calculator.compute_all_ratios(latest_annual)

        ratios_ttm = {}
        if ttm_record:
            ratios_ttm = self.calculator.compute_all_ratios(ttm_record)

        q_growth = {}
        if not quarterly_reports.empty:
            q_records = quarterly_reports.to_dict("records")
            q_growth = self.calculator.compute_quarterly_growth(q_records)

        a_growth = {}
        if not annual_reports.empty:
            a_records = annual_reports.to_dict("records")
            a_growth = self.calculator.compute_annual_growth(a_records)

        piotroski = {}
        if not annual_reports.empty and len(annual_reports) >= 2:
            a_records = annual_reports.to_dict("records")
            piotroski = self.calculator.compute_piotroski(a_records[0], a_records[1])

        altman = {}
        target = latest_annual or latest_quarterly
        if target:
            altman = self.calculator.compute_altman(target)

        pe = None
        if info.get("market_cap") and latest_quarterly and latest_quarterly.get("eps"):
            ttm_eps = None
            q_recs = quarterly_reports.to_dict("records") if not quarterly_reports.empty else []
            if len(q_recs) >= 4:
                ttm_eps = sum(self.calculator._safe(r.get("eps")) for r in q_recs[:4] if self.calculator._safe(r.get("eps")) is not None)
            if ttm_eps and ttm_eps != 0:
                pe = self.calculator._safe(info["market_cap"]) / ttm_eps

        peg = None
        if pe is not None:
            eg = a_growth.get("eps_growth") or q_growth.get("eps_yoy") or q_growth.get("eps_qoq")
            if eg is not None and eg > 0:
                peg = self.calculator.compute_peg(pe, eg)

        gross_margin = ratios_q.get("gross_margin") or ratios_a.get("gross_margin")

        fcf_annual = None
        if latest_annual:
            ocf_a = self.calculator._safe(latest_annual.get("operating_cash_flow"))
            cap_a = self.calculator._safe(latest_annual.get("capex"))
            if ocf_a is not None and cap_a is not None:
                fcf_annual = ocf_a + cap_a

        def _get_q_fy_str(rec):
            if not rec:
                return "N/A"
            q = rec.get("quarter")
            fy = rec.get("financial_year")
            if q and fy:
                return f"Q{q} FY{fy}"
            if fy:
                return f"FY{fy}"
            if q:
                return f"Q{q}"
            return "N/A"

        def _make_detail(metric_name, val, rec, default_source="screener_official"):
            c_name = (rec.get("company") if rec else None) or info.get("company_name") or symbol
            p_type = (rec.get("period") if rec else None) or "N/A"
            q_fy = _get_q_fy_str(rec)
            r_date = (rec.get("report_date") if rec else None) or "N/A"
            is_c = bool(rec.get("consolidated", 1)) if rec else True
            u_str = (rec.get("unit") if rec else None) or "INR_Crores"
            s_url = (rec.get("source_url") if rec else None) or "N/A"
            s_type = (rec.get("source_type") if rec else None) or default_source

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

        target_rec = latest_quarterly or latest_annual
        target_a_rec = latest_annual or latest_quarterly

        metric_details = {
            "Revenue": _make_detail("Revenue", (latest_quarterly or {}).get("revenue") or (latest_annual or {}).get("revenue"), target_rec),
            "PAT": _make_detail("PAT", (latest_quarterly or {}).get("pat") or (latest_annual or {}).get("pat"), target_rec),
            "EPS": _make_detail("EPS", (latest_quarterly or {}).get("eps") or (latest_annual or {}).get("eps"), target_rec),
            "EBIT": _make_detail("EBIT", (latest_quarterly or {}).get("ebit") or (latest_annual or {}).get("ebit"), target_rec),
            "ROE": _make_detail("ROE", ratios_q.get("roe") or ratios_a.get("roe"), target_rec),
            "ROCE": _make_detail("ROCE", ratios_q.get("roce") or ratios_a.get("roce"), target_rec),
            "ROA": _make_detail("ROA", ratios_q.get("roa") or ratios_a.get("roa"), target_rec),
            "DebtEquity": _make_detail("DebtEquity", ratios_q.get("debt_equity") or ratios_a.get("debt_equity"), target_rec),
            "OPM": _make_detail("OPM", ratios_q.get("opm") or ratios_a.get("opm"), target_rec),
            "NPM": _make_detail("NPM", ratios_q.get("npm") or ratios_a.get("npm"), target_rec),
            "GrossMargin": _make_detail("GrossMargin", gross_margin, target_rec),
            "OperatingCashFlow": _make_detail("OperatingCashFlow", ratios_ttm.get("fcf") or (latest_quarterly or {}).get("operating_cash_flow") or (latest_annual or {}).get("operating_cash_flow"), target_rec),
            "FreeCashFlow": _make_detail("FreeCashFlow", ratios_ttm.get("fcf") or fcf_annual, target_rec),
            "PE": _make_detail("PE", pe, target_rec),
            "PEG": _make_detail("PEG", peg, target_rec),
            "Piotroski": _make_detail("Piotroski", piotroski.get("score") if isinstance(piotroski, dict) else None, target_a_rec),
            "Altman": _make_detail("Altman", altman.get("value") if isinstance(altman, dict) else None, target_rec),
        }

        slug = self._ticker_to_slug(symbol)
        ir_url = self._get_ir_url(slug)
        html = self._get(ir_url) if ir_url else None
        sh_info = {}
        # Use cached shareholding from get_company_info if available
        for k in ("Promoter_Pct", "FII_Pct", "DII_Pct", "Govt_Pct", "Public_Pct",
                  "Institutional_Pct", "Shareholders_Count", "Shareholding_Period",
                  "Shareholding_Table", "Shareholding_History"):
            v = info.get(k)
            if v is not None:
                sh_info[k] = v
        if html and not sh_info.get("Promoter_Pct"):
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            sh_info = self._extract_shareholding(soup)

        result = {
            "Symbol": symbol,
            "Company": info.get("company_name"),
            "Sector": info.get("sector"),
            "Industry": info.get("industry"),
            "MarketCap": info.get("market_cap"),
            "PE": pe,
            "PEG": peg,
            "ForwardPE": None,
            "PriceSales": None,
            "ROE": ratios_q.get("roe") or ratios_a.get("roe"),
            "ROCE": ratios_q.get("roce") or ratios_a.get("roce"),
            "ROA": ratios_q.get("roa") or ratios_a.get("roa"),
            "RevenueGrowth": a_growth.get("revenue_growth") or q_growth.get("sales_yoy"),
            "Revenue_Growth": a_growth.get("revenue_growth") or q_growth.get("sales_yoy"),
            "EarningsGrowth": a_growth.get("eps_growth") or q_growth.get("eps_yoy"),
            "EPS_Growth": a_growth.get("eps_growth") or q_growth.get("eps_yoy"),
            "EarningsQuarterlyGrowth": q_growth.get("eps_yoy") or q_growth.get("eps_qoq"),
            "DebtEquity": ratios_q.get("debt_equity") or ratios_a.get("debt_equity"),
            "ProfitMargin": ratios_q.get("npm") or ratios_a.get("npm"),
            "GrossMargin": gross_margin,
            "DividendYield": None,
            "NetIncome": (latest_quarterly or {}).get("pat"),
            "TotalAssets": (latest_quarterly or {}).get("assets") or (latest_annual or {}).get("assets"),
            "TotalLiabilities": (latest_quarterly or {}).get("liabilities") or (latest_annual or {}).get("liabilities"),
            "TotalDebt": (latest_annual or {}).get("debt") or (latest_quarterly or {}).get("debt"),
            "TotalCash": (latest_annual or {}).get("cash_and_cash_equivalents") or (latest_quarterly or {}).get("cash_and_cash_equivalents"),
            "CashAndCashEquivalents": (latest_annual or {}).get("cash_and_cash_equivalents") or (latest_quarterly or {}).get("cash_and_cash_equivalents"),
            "CurrentAssets": (latest_quarterly or {}).get("current_assets") or (latest_annual or {}).get("current_assets"),
            "CurrentLiabilities": (latest_quarterly or {}).get("current_liabilities") or (latest_annual or {}).get("current_liabilities"),
            "TotalStockholderEquity": (latest_quarterly or {}).get("equity") or (latest_annual or {}).get("equity"),
            "OperatingCashFlow": ratios_ttm.get("fcf") or (latest_quarterly or {}).get("operating_cash_flow") or (latest_annual or {}).get("operating_cash_flow"),
            "OperatingCashFlowTTM": ttm_record.get("operating_cash_flow") if ttm_record else None,
            "OperatingCashFlowAnnual": (latest_annual or {}).get("operating_cash_flow"),
            "FreeCashFlow": ratios_ttm.get("fcf"),
            "FreeCashFlowTTM": ttm_record.get("fcf") if ttm_record else None,
            "FreeCashFlowAnnual": fcf_annual,
            "GrossMargins": gross_margin,
            "EBIT": (latest_quarterly or {}).get("ebit") or (latest_annual or {}).get("ebit"),
            "CurrentRatio": None,
            "QuickRatio": None,
            "BookValue": None,
            "SharesOutstanding": info.get("sharesOutstanding"),
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
            "TotalCash": None,
            "EnterpriseValue": None,
            "quarterly_financials": q_fin if q_fin is not None else pd.DataFrame(),
            "annual_financials": annual_income if annual_income is not None else pd.DataFrame(),
            "quarterly_balance_sheet": q_balance if q_balance is not None else pd.DataFrame(),
            "balance_sheet": annual_balance if annual_balance is not None else pd.DataFrame(),
            "cashflow": annual_cashflow if annual_cashflow is not None else pd.DataFrame(),
            "quarterly_meta": {"source": "company_ir", "periods": list(q_fin.columns) if q_fin is not None and not q_fin.empty else []},
            "quarterly_roe": ratios_q.get("roe"),
            "quarterly_roa": ratios_q.get("roa"),
            "quarterly_debt_equity": ratios_q.get("debt_equity"),
            "fundamentals_source": "company_ir",
            "quarterly_growth": q_growth,
            "annual_growth": a_growth,
            "piotroski_f_score": piotroski,
            "altman_z_score": altman,
            "Piotroski_FScore": piotroski.get("score") if isinstance(piotroski, dict) else None,
            "Altman_ZScore": {"value": altman.get("value") if isinstance(altman, dict) else None,
                              "available": altman.get("available", False) if isinstance(altman, dict) else False},
            "Piotroski": piotroski.get("score") if isinstance(piotroski, dict) else None,
            "Altman": altman,
            "metric_details": metric_details,
        }

        return result


class ReportParser:
    """Helper class for label extraction and period normalization."""

    INCOME_LABEL_MAP = OfficialReportsProvider.INCOME_LABEL_RENAME
    BALANCE_LABEL_MAP = OfficialReportsProvider.BALANCE_LABEL_RENAME
    CASHFLOW_LABEL_MAP = OfficialReportsProvider.CASHFLOW_LABEL_RENAME

    @classmethod
    def find_label(cls, df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
        if df is None or df.empty:
            return None
        index_labels = [str(idx) for idx in df.index]
        for candidate in candidates:
            for idx_label in index_labels:
                if candidate.lower() in idx_label.lower():
                    return idx_label
        return None

    @classmethod
    def _safe_float(cls, value) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            f = float(value)
            if math.isnan(f) or math.isinf(f):
                return None
            return f
        s = str(value).strip().replace(",", "").replace("%", "").replace("\u20b9", "").replace("$", "").replace("\u2014", "").replace("\u2013", "").strip()
        if not s:
            return None
        try:
            f = float(s)
            if math.isnan(f) or math.isinf(f):
                return None
            return f
        except (ValueError, TypeError):
            return None

    @classmethod
    def extract_income_value(cls, df: pd.DataFrame, metric: str, period) -> Optional[float]:
        if df is None or df.empty:
            return None
        label = cls.find_label(df, cls.INCOME_LABEL_MAP.get(metric, []))
        if label is None:
            return None
        try:
            val = df.loc[label, period]
            return cls._safe_float(val)
        except Exception:
            return None

    @classmethod
    def extract_balance_value(cls, df: pd.DataFrame, metric: str, period) -> Optional[float]:
        if df is None or df.empty:
            return None
        label = cls.find_label(df, cls.BALANCE_LABEL_MAP.get(metric, []))
        if label is None:
            return None
        try:
            val = df.loc[label, period]
            return cls._safe_float(val)
        except Exception:
            return None

    @classmethod
    def extract_cashflow_value(cls, df: pd.DataFrame, metric: str, period) -> Optional[float]:
        if df is None or df.empty:
            return None
        label = cls.find_label(df, cls.CASHFLOW_LABEL_MAP.get(metric, []))
        if label is None:
            return None
        try:
            val = df.loc[label, period]
            return cls._safe_float(val)
        except Exception:
            return None

    @classmethod
    def normalize_period(cls, period_str: str) -> Optional[str]:
        if period_str is None:
            return None
        s = str(period_str).strip()
        if not s:
            return None
        try:
            dt = pd.to_datetime(s)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return s

    @classmethod
    def is_quarterly_period(cls, period_str: str) -> bool:
        s = cls.normalize_period(period_str)
        if s is None:
            return False
        try:
            dt = pd.to_datetime(s)
            month = dt.month
            return month in [3, 6, 9, 12]
        except Exception:
            return False

    @classmethod
    def derive_financial_year(cls, period_str: str, quarter: Optional[int] = None) -> Optional[int]:
        return _ReportHelpers.derive_financial_year(period_str, quarter)

    @classmethod
    def derive_quarter(cls, period_str: str) -> Optional[int]:
        return _ReportHelpers.derive_quarter(period_str)


class _ReportHelpers:
    """Internal helpers shared by OfficialReportsProvider."""

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
        """Derive FY from an annual column label.

        Handles both:
          - 'FY23' format  → 2023
          - 'Mar 2024' format (company IR page columns) → 2024
        """
        s = str(period_str).strip() if period_str else ""
        if not s:
            return None
        m = re.match(r'^[Ff][Yy]\s*(\d{2,4})$', s)
        if m:
            yr = int(m.group(1))
            if yr < 100:
                yr += 2000
            return yr
        # Handle 'Mar 2024' / 'Dec 2023' style annual column labels
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


# ── module-level helpers ─────────────────────────────────────────────────────

def _find_in_normalized(df: pd.DataFrame, canonical: str) -> Optional[float]:
    """Find a canonical label in a normalized DataFrame index and return its first-column value."""
    if df is None or df.empty:
        return None
    df_idx = [str(i) for i in df.index]
    cl = canonical.lower()
    for idx_label in df_idx:
        if cl in idx_label.lower():
            try:
                first_col = df.columns[0]
                val = df.loc[idx_label, first_col]
                return FinancialCalculator._safe(val)
            except Exception:
                continue
    return None


def _extract_balance(df: Optional[pd.DataFrame], canonical: str) -> Optional[float]:
    if df is None or df.empty:
        return None
    return _find_in_normalized(df, canonical)


def _sum_balance(df: Optional[pd.DataFrame], candidates: List[str]) -> Optional[float]:
    """Sum multiple balance-sheet line items (e.g. Equity Capital + Reserves)."""
    if df is None or df.empty:
        return None
    total = 0.0
    found_any = False
    for canonical in candidates:
        v = _find_in_normalized(df, canonical)
        if v is not None:
            total += v
            found_any = True
    return total if found_any else None


def _extract_cf(df: Optional[pd.DataFrame], canonical: str) -> Optional[float]:
    if df is None or df.empty:
        return None
    return _find_in_normalized(df, canonical)


_CANONICAL_TO_KEY = {
    "Total Revenue": "revenue",
    "Operating Income": "operating_profit",
    "EBIT": "ebit",
    "EBITDA": "ebit",
    "Net Income": "pat",
    "Gross Profit": "gross_profit",
}
_CANONICAL_BS_TO_KEY = {
    "Total Assets": "total_assets",
    "Total Liab": "total_liabilities",
    "Total Debt": "total_debt",
    "Equity Capital": "equity",
    "Reserves": "retained_earnings",
    "Borrowings": "total_debt",
}


def _canonical_to_key(canonical: str) -> str:
    return _CANONICAL_TO_KEY.get(canonical, canonical.lower().replace(" ", "_"))


def _canonical_bs_to_key(canonical: str) -> str:
    return _CANONICAL_BS_TO_KEY.get(canonical, canonical.lower().replace(" ", "_"))
