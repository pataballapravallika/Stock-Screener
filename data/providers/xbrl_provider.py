import os
from typing import Any, Dict, List, Optional

from data.providers.base_provider import BaseFundamentalProvider, ReportIngestionMixin
from data.parsers.xbrl_parser import XBRLParser
from data.calculations.financial_calculator import FinancialCalculator
from data.database import (
    init_db, save_company_info, get_company_info,
    save_fundamental_report, get_latest_quarterly_reports,
    get_latest_annual_reports, save_ttm_record, get_ttm_record
)


class XBRLProvider(BaseFundamentalProvider, ReportIngestionMixin):
    """Fundamental provider that ingests XBRL instance or inline documents.

    Accepts:
      - Local file paths (.xml, .xbrl, .html)
      - URLs (downloaded first)

    Extracts the 13 standard fields and stores normalized records in SQLite.
    """

    def __init__(self):
        init_db()
        self.parser = XBRLParser()
        self.calculator = FinancialCalculator()

    def get_company_info(self, symbol: str) -> Dict[str, Any]:
        cached = get_company_info(symbol)
        if cached:
            return {
                "ticker": symbol,
                "company_name": cached.get("company_name"),
                "sector": cached.get("sector"),
                "industry": cached.get("industry"),
                "market_cap": cached.get("market_cap"),
                "sharesOutstanding": cached.get("shares_outstanding"),
            }
        return {}

    def _fetch_raw(self, source: str) -> Dict[str, Any]:
        if self.is_file(source):
            return self.parser.parse_file(source)
        if self.is_url(source):
            try:
                import requests
                resp = requests.get(source, timeout=30)
                if resp.status_code == 200:
                    return self.parser.parse_bytes(resp.content, source)
            except Exception:
                pass
        return {}

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
            "current_assets": raw.get("current_assets"),
            "liabilities": raw.get("total_liabilities"),
            "current_liabilities": raw.get("current_liabilities"),
            "working_capital": None,
            "debt": raw.get("total_debt"),
            "operating_cash_flow": raw.get("operating_cash_flow"),
            "capex": raw.get("capex"),
            "gross_profit": None,
            "retained_earnings": None,
            "source": "xbrl",
        }
        ca = record.get("current_assets")
        cl = record.get("current_liabilities")
        if ca is not None and cl is not None:
            record["working_capital"] = ca - cl
        save_fundamental_report(record)

    def ingest_xbrl(self, symbol: str, source: str, period: str, report_date: str, financial_year: int, quarter: Optional[int] = None):
        raw = self._fetch_raw(source)
        if not raw:
            return False
        self._store_record(symbol, period, report_date, financial_year, quarter, raw)
        return True

    def get_quarterly_financials(self, symbol: str) -> Optional[Any]:
        reports = get_latest_quarterly_reports(symbol, n=8)
        if reports.empty:
            return None
        return self._reports_to_income_df(reports)

    def get_annual_financials(self, symbol: str) -> Optional[Any]:
        reports = get_latest_annual_reports(symbol, n=5)
        if reports.empty:
            return None
        return self._reports_to_income_df(reports)

    def get_quarterly_balance_sheet(self, symbol: str) -> Optional[Any]:
        reports = get_latest_quarterly_reports(symbol, n=8)
        if reports.empty:
            return None
        return self._reports_to_balance_df(reports)

    def get_annual_balance_sheet(self, symbol: str) -> Optional[Any]:
        reports = get_latest_annual_reports(symbol, n=5)
        if reports.empty:
            return None
        return self._reports_to_balance_df(reports)

    def get_quarterly_cashflow(self, symbol: str) -> Optional[Any]:
        reports = get_latest_quarterly_reports(symbol, n=8)
        if reports.empty:
            return None
        return self._reports_to_cashflow_df(reports)

    def get_annual_cashflow(self, symbol: str) -> Optional[Any]:
        reports = get_latest_annual_reports(symbol, n=5)
        if reports.empty:
            return None
        return self._reports_to_cashflow_df(reports)

    def get_source(self) -> str:
        return "xbrl"

    def build_fundamentals_dict(self, symbol: str) -> Dict[str, Any]:
        info = self.get_company_info(symbol)
        q_reports = get_latest_quarterly_reports(symbol, n=8)
        a_reports = get_latest_annual_reports(symbol, n=5)
        ttm_record = get_ttm_record(symbol, "ttm")

        latest_q = q_reports.iloc[0].to_dict() if not q_reports.empty else {}
        latest_a = a_reports.iloc[0].to_dict() if not a_reports.empty else {}

        ratios_q = self.calculator.compute_all_ratios(latest_q) if latest_q else {}
        ratios_a = self.calculator.compute_all_ratios(latest_a) if latest_a else {}
        ratios_ttm = self.calculator.compute_all_ratios(ttm_record) if ttm_record else {}

        q_records = q_reports.to_dict("records") if not q_reports.empty else []
        a_records = a_reports.to_dict("records") if not a_reports.empty else []

        q_growth = self.calculator.compute_quarterly_growth(q_records)
        a_growth = self.calculator.compute_annual_growth(a_records)

        piotroski = {}
        if len(a_records) >= 2:
            piotroski = self.calculator.compute_piotroski(a_records[0], a_records[1])

        altman = {}
        target = latest_a or latest_q
        if target:
            altman = self.calculator.compute_altman(target)

        pe = None
        if info.get("market_cap") and latest_q and latest_q.get("eps"):
            ttm_eps = None
            if len(q_records) >= 4:
                ttm_eps = sum(self.calculator._safe(r.get("eps")) for r in q_records[:4] if self.calculator._safe(r.get("eps")) is not None)
            if ttm_eps and ttm_eps != 0:
                pe = self.calculator._safe(info["market_cap"]) / ttm_eps

        peg = None
        if pe is not None:
            eg = a_growth.get("eps_growth") or q_growth.get("eps_yoy") or q_growth.get("eps_qoq")
            if eg is not None and eg > 0:
                peg = self.calculator.compute_peg(pe, eg)

        gross_margin = ratios_q.get("gross_margin") or ratios_a.get("gross_margin")

        fcf_annual = None
        if latest_a:
            ocf_a = self.calculator._safe(latest_a.get("operating_cash_flow"))
            cap_a = self.calculator._safe(latest_a.get("capex"))
            if ocf_a is not None and cap_a is not None:
                fcf_annual = ocf_a + cap_a

        return {
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
            "RevenueGrowth": a_growth.get("revenue_growth"),
            "EarningsGrowth": a_growth.get("eps_growth"),
            "EarningsQuarterlyGrowth": q_growth.get("eps_yoy") or q_growth.get("eps_qoq"),
            "DebtEquity": ratios_q.get("debt_equity") or ratios_a.get("debt_equity"),
            "ProfitMargin": ratios_q.get("npm") or ratios_a.get("npm"),
            "GrossMargin": gross_margin,
            "DividendYield": None,
            "NetIncome": latest_q.get("pat"),
            "TotalAssets": latest_q.get("assets") or latest_a.get("assets"),
            "TotalDebt": latest_q.get("debt") or latest_a.get("debt"),
            "OperatingCashFlow": ratios_ttm.get("fcf") or latest_q.get("operating_cash_flow") or latest_a.get("operating_cash_flow"),
            "OperatingCashFlowTTM": ttm_record.get("operating_cash_flow") if ttm_record else None,
            "OperatingCashFlowAnnual": latest_a.get("operating_cash_flow"),
            "FreeCashFlow": ratios_ttm.get("fcf"),
            "FreeCashFlowTTM": ttm_record.get("fcf") if ttm_record else None,
            "FreeCashFlowAnnual": fcf_annual,
            "GrossMargins": gross_margin,
            "EBIT": latest_q.get("ebit") or latest_a.get("ebit"),
            "CurrentRatio": None,
            "QuickRatio": None,
            "BookValue": None,
            "SharesOutstanding": info.get("sharesOutstanding"),
            "FloatShares": None,
            "InstitutionsPercentHeld": None,
            "InsidersPercentHeld": None,
            "SharesShort": None,
            "SharesShortPriorMonth": None,
            "TotalCash": None,
            "EnterpriseValue": None,
            "quarterly_financials": self.get_quarterly_financials(symbol) or _empty_df(),
            "annual_financials": self.get_annual_financials(symbol) or _empty_df(),
            "quarterly_balance_sheet": self.get_quarterly_balance_sheet(symbol) or _empty_df(),
            "balance_sheet": self.get_annual_balance_sheet(symbol) or _empty_df(),
            "cashflow": self.get_annual_cashflow(symbol) or _empty_df(),
            "quarterly_growth": q_growth,
            "annual_growth": a_growth,
            "piotroski_f_score": piotroski,
            "altman_z_score": altman,
            "fundamentals_source": "xbrl",
        }

    def _reports_to_income_df(self, reports: Any) -> Any:
        import pandas as pd
        if reports is None or reports.empty:
            return pd.DataFrame()
        rows = {
            "Total Revenue": [],
            "Operating Profit": [],
            "EBIT": [],
            "Net Income": [],
            "EPS": [],
        }
        cols = []
        for _, r in reports.iterrows():
            cols.append(r.get("report_date", ""))
            rows["Total Revenue"].append(r.get("revenue"))
            rows["Operating Profit"].append(r.get("operating_profit"))
            rows["EBIT"].append(r.get("ebit"))
            rows["Net Income"].append(r.get("pat"))
            rows["EPS"].append(r.get("eps"))
        return pd.DataFrame(rows, index=cols).T

    def _reports_to_balance_df(self, reports: Any) -> Any:
        import pandas as pd
        if reports is None or reports.empty:
            return pd.DataFrame()
        rows = {
            "Total Assets": [],
            "Current Assets": [],
            "Total Liabilities": [],
            "Current Liabilities": [],
            "Shareholders' Equity": [],
            "Total Debt": [],
        }
        cols = []
        for _, r in reports.iterrows():
            cols.append(r.get("report_date", ""))
            rows["Total Assets"].append(r.get("assets"))
            rows["Current Assets"].append(r.get("current_assets"))
            rows["Total Liabilities"].append(r.get("liabilities"))
            rows["Current Liabilities"].append(r.get("current_liabilities"))
            rows["Shareholders' Equity"].append(r.get("equity"))
            rows["Total Debt"].append(r.get("debt"))
        return pd.DataFrame(rows, index=cols).T

    def _reports_to_cashflow_df(self, reports: Any) -> Any:
        import pandas as pd
        if reports is None or reports.empty:
            return pd.DataFrame()
        rows = {
            "Operating Cash Flow": [],
            "Capital Expenditure": [],
        }
        cols = []
        for _, r in reports.iterrows():
            cols.append(r.get("report_date", ""))
            rows["Operating Cash Flow"].append(r.get("operating_cash_flow"))
            rows["Capital Expenditure"].append(r.get("capex"))
        return pd.DataFrame(rows, index=cols).T


def _empty_df():
    import pandas as pd
    return pd.DataFrame()
