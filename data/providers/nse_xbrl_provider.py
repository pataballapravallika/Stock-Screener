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
from data.providers.official_reports_provider import _ReportHelpers
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
)


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
                resp = session.get(url, params=params, headers=headers, timeout=25)
                if resp.status_code in (401, 403, 500):
                    session.get(self.NSE_BASE, timeout=15)
                    continue
                resp.raise_for_status()
                return resp.json()
            except Exception:
                if attempt < 1:
                    time.sleep(1.5)
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
            return {
                "ticker": symbol,
                "company_name": cached.get("company_name"),
                "sector": cached.get("sector"),
                "industry": cached.get("industry"),
                "market_cap": cached.get("market_cap"),
                "sharesOutstanding": cached.get("shares_outstanding"),
            }

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

        # Fallback for sector, industry, marketCap if missing from NSE quote endpoint
        if not sector or not industry or not mcap:
            try:
                from data.providers.official_reports_provider import OfficialReportsProvider
                off_info = OfficialReportsProvider().get_company_info(symbol)
                if off_info:
                    company_name = company_name or off_info.get("company_name")
                    sector = sector or off_info.get("sector")
                    industry = industry or off_info.get("industry")
                    mcap = mcap or off_info.get("market_cap")
                    shares = shares or off_info.get("sharesOutstanding")
            except Exception:
                pass

        if not sector or sector == "Unknown":
            from data.sector_data import get_standard_sector
            sector = get_standard_sector(symbol)

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
                xbrl_url = f"https://nsearchives.nseindia.com/corporate/XBRL/{clean}_{dt}.xml"

                filing_dict = {
                    "symbol": clean,
                    "company_name": item.get("symbol", clean),
                    "period_end": dt,
                    "attchmntText": item.get("attchmntText"),
                    "xbrl_url": xbrl_url,
                    "hasXbrl": has_xbrl,
                    "is_consolidated": "consolidated" in text or "consol" in text,
                }
                xml_text = self._fetch_url_text(xbrl_url)
                if xml_text:
                    parsed = self._parse_xbrl_stdlib(xml_text, symbol, xbrl_url)
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
        if val is None:
            return None
        if is_eps:
            return val
        if abs(val) >= 1000000:
            return val / 10000000.0
        return val

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

        def _get(key_list: List[str], is_eps: bool = False) -> Optional[float]:
            for k in key_list:
                for map_k, map_v in data_map.items():
                    if k.lower() in map_k.lower():
                        flt = self._to_float(map_v)
                        if flt is not None:
                            return self._to_crores(flt, is_eps=is_eps)
            return None

        revenue = _get(["RevenueFromOperations", "IncomeFromOperations", "TotalRevenue", "Income", "Revenue"])
        pat = _get(["ProfitLossForPeriod", "ProfitAfterTax", "NetProfit", "ProfitLossFromOrdinaryActivitiesAfterTax"])
        eps = _get(["DilutedEarningsLossPerShare", "BasicEarningsLossPerShare", "DilutedEPS", "BasicEPS", "EPS"], is_eps=True)
        ebit = _get(["ProfitBeforeTax", "ProfitLossBeforeTax", "EBIT"])
        total_assets = _get(["TotalAssets", "Assets"])
        equity = _get(["TotalEquity", "Equity", "PaidUpEquityShareCapital", "ShareCapital"])
        total_liab = _get(["TotalLiabilities", "Liabilities"])
        curr_assets = _get(["TotalCurrentAssets", "CurrentAssets"])
        curr_liab = _get(["TotalCurrentLiabilities", "CurrentLiabilities"])
        capex = _get(["PurchaseOfPropertyPlantAndEquipment", "CapEx", "CapitalExpenditure"])
        ocf = _get(["NetCashFlowsFromUsedInOperatingActivities", "OperatingCashFlow", "CashFlowFromOperatingActivities"])

        is_consol = any("consolidated" in str(k) or "consol" in str(k) for k in data_map.keys())

        return {
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
        }

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

        assets = self._to_crores(_get_attr("bs_total_assets"))
        equity = self._to_crores(_get_attr("bs_equity"))
        liab = self._to_crores(_get_attr("bs_total_liabilities"))
        c_assets = self._to_crores(_get_attr("bs_current_assets"))
        c_liab = self._to_crores(_get_attr("bs_current_liabilities"))

        capex = self._to_crores(_get_attr("cf_capex"))
        ocf = self._to_crores(_get_attr("cf_operating_cash_flow"))

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
            debt=(liab - equity) if liab and equity else None,
            operating_cash_flow=ocf,
            capex=capex,
            gross_profit=None,
            cogs=None,
            retained_earnings=None,
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
        q_df = get_latest_quarterly_reports(symbol, limit=1)
        a_df = get_latest_annual_reports(symbol, limit=1)
        if q_df.empty or a_df.empty:
            self.ingest_from_nse(symbol)

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

        mcap = info.get("market_cap")
        if not mcap:
            try:
                from data.providers.official_reports_provider import OfficialReportsProvider
                off_info = OfficialReportsProvider().get_company_info(symbol)
                mcap = off_info.get("market_cap")
            except Exception:
                pass

        if mcap:
            info["market_cap"] = mcap
            latest_q["market_cap"] = mcap
            latest_a["market_cap"] = mcap
            ratios = self.calculator.compute_all_ratios(latest_q, latest_a, ttm_rec or {})

        eps_g = q_growth.get("eps_qoq") or a_growth.get("eps_yoy")
        peg = self.calculator.compute_peg(ratios.get("pe"), eps_g)

        # Retrieve shareholding from official disclosures only
        sh_info = {}
        try:
            from data.providers.official_reports_provider import OfficialReportsProvider
            off_dict = OfficialReportsProvider().build_fundamentals_dict(symbol)
            if off_dict:
                sh_info = off_dict
        except Exception:
            pass

        result = {
            "Symbol": symbol,
            "Company": info.get("company_name", symbol),
            "Sector": info.get("sector", "N/A"),
            "Industry": info.get("industry", "N/A"),
            "MarketCap": mcap,
            "Revenue": rev,
            "PAT": pat,
            "EPS": eps,
            "EBIT": ebit,
            "ROE": ratios.get("roe"),
            "ROCE": ratios.get("roce"),
            "ROA": ratios.get("roa"),
            "DebtEquity": ratios.get("debt_equity"),
            "OPM": ratios.get("opm"),
            "NPM": ratios.get("npm"),
            "FreeCashFlow": ratios.get("fcf"),
            "PE": ratios.get("pe"),
            "PEG": peg,
            "Piotroski": piotroski.get("score") if isinstance(piotroski, dict) else None,
            "Altman": altman,
            "Sales_QoQ": q_growth.get("sales_qoq"),
            "Sales_YoY": q_growth.get("sales_yoy"),
            "PAT_QoQ": q_growth.get("pat_qoq"),
            "PAT_YoY": q_growth.get("pat_yoy"),
            "EPS_QoQ": q_growth.get("eps_qoq"),
            "EPS_YoY": q_growth.get("eps_yoy"),
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
            "InsidersPercentHeld": sh_info.get("Promoter_Pct"),
            "InstitutionsPercentHeld": sh_info.get("Institutional_Pct"),
            "fundamentals_source": "nse_xbrl",
        }

        return result
