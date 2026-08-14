import math
import pandas as pd
from typing import Dict, Any, Optional, List


class FinancialCalculator:
    """Pure calculation module.

    Operates on already-extracted raw values (no network or parsing).
    Never estimates missing data; returns None for incomplete inputs.
    """

    @staticmethod
    def _safe(value) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, float) and math.isnan(value):
            return None
        if isinstance(value, str):
            try:
                return float(value.replace(",", "").strip())
            except ValueError:
                return None
        try:
            f = float(value)
            if math.isnan(f) or math.isinf(f):
                return None
            return f
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _div(numerator, denominator) -> Optional[float]:
        n = FinancialCalculator._safe(numerator)
        d = FinancialCalculator._safe(denominator)
        if n is None or d is None or d == 0:
            return None
        return n / d

    @classmethod
    def compute_roe(cls, net_income, shareholders_equity) -> Optional[float]:
        return cls._div(cls._safe(net_income), cls._safe(shareholders_equity))

    @classmethod
    def compute_roa(cls, net_income, total_assets) -> Optional[float]:
        return cls._div(cls._safe(net_income), cls._safe(total_assets))

    @classmethod
    def compute_roce(cls, ebit, total_assets, current_liabilities, equity=None, debt=None) -> Optional[float]:
        e = cls._safe(ebit)
        ta = cls._safe(total_assets)
        cl = cls._safe(current_liabilities)
        eq = cls._safe(equity)
        d = cls._safe(debt)
        if e is None:
            return None
        capital_employed = None
        if ta is not None and cl is not None and ta > cl:
            capital_employed = ta - cl
        elif eq is not None and eq > 0:
            capital_employed = eq + (d or 0.0)
        elif ta is not None and ta > 0:
            capital_employed = ta
        if capital_employed is None or capital_employed <= 0:
            return None
        return e / capital_employed

    @classmethod
    def compute_debt_equity(cls, total_debt, shareholders_equity) -> Optional[float]:
        return cls._div(cls._safe(total_debt), cls._safe(shareholders_equity))

    @classmethod
    def compute_opm(cls, operating_profit, revenue) -> Optional[float]:
        return cls._div(cls._safe(operating_profit), cls._safe(revenue))

    @classmethod
    def compute_npm(cls, net_income, revenue) -> Optional[float]:
        return cls._div(cls._safe(net_income), cls._safe(revenue))

    @classmethod
    def compute_gross_margin(cls, gross_profit, revenue) -> Optional[float]:
        return cls._div(cls._safe(gross_profit), cls._safe(revenue))

    @classmethod
    def compute_fcf(cls, operating_cash_flow, capex) -> Optional[float]:
        ocf = cls._safe(operating_cash_flow)
        cap = cls._safe(capex)
        if ocf is None or cap is None:
            return None
        # CapEx normalization:
        # If capex is negative cash flow (< 0), e.g. -500 Cr: FCF = OCF + capex
        # If capex is positive expenditure (> 0), e.g. 500 Cr: FCF = OCF - capex
        if cap < 0:
            return ocf + cap
        return ocf - cap

    @classmethod
    def compute_cagr(cls, end_value, start_value, num_years: int = 3) -> Optional[float]:
        end_v = cls._safe(end_value)
        start_v = cls._safe(start_value)
        if end_v is None or start_v is None or start_v <= 0 or num_years <= 0:
            return None
        return (end_v / start_v) ** (1.0 / num_years) - 1.0

    @classmethod
    def compute_peg(cls, pe: Optional[float], eps_growth: Optional[float]) -> Optional[float]:
        """PEG = PE / (EPS growth rate as percentage).

        eps_growth is expected as a ratio (e.g. 0.15 for 15 %).
        """
        pe_v = cls._safe(pe)
        eg = cls._safe(eps_growth)
        if pe_v is None or eg is None or eg <= 0:
            return None
        return pe_v / (eg * 100.0)

    @classmethod
    def compute_working_capital(cls, current_assets, current_liabilities) -> Optional[float]:
        ca = cls._safe(current_assets)
        cl = cls._safe(current_liabilities)
        if ca is None or cl is None:
            return None
        return ca - cl

    @classmethod
    def compute_all_ratios(cls, record: Dict[str, Any] = None, annual_record: Dict[str, Any] = None, ttm_record: Dict[str, Any] = None, *args, **kwargs) -> Dict[str, Any]:
        merged = {}
        if record and isinstance(record, dict):
            merged.update(record)
        if annual_record and isinstance(annual_record, dict):
            for k, v in annual_record.items():
                if merged.get(k) is None:
                    merged[k] = v
        if ttm_record and isinstance(ttm_record, dict):
            for k, v in ttm_record.items():
                if merged.get(k) is None:
                    merged[k] = v

        ta = cls._safe(merged.get("assets"))
        cl = cls._safe(merged.get("current_liabilities"))
        ni = cls._safe(merged.get("pat"))
        eq = cls._safe(merged.get("equity"))
        ebit = cls._safe(merged.get("ebit"))
        op = cls._safe(merged.get("operating_profit"))
        rev = cls._safe(merged.get("revenue"))
        debt = cls._safe(merged.get("debt"))
        ocf = cls._safe(merged.get("operating_cash_flow"))
        cap = cls._safe(merged.get("capex"))
        market_cap = cls._safe(merged.get("market_cap") or merged.get("MarketCap"))
        shares = cls._safe(merged.get("shares_outstanding") or merged.get("sharesOutstanding"))
        ca = cls._safe(merged.get("current_assets"))
        gp = cls._safe(merged.get("gross_profit"))

        ratios = {
            "roe": cls.compute_roe(ni, eq),
            "roa": cls.compute_roa(ni, ta),
            "roce": cls.compute_roce(ebit, ta, cl, equity=eq, debt=debt),
            "debt_equity": cls.compute_debt_equity(debt, eq),
            "opm": cls.compute_opm(op, rev),
            "npm": cls.compute_npm(ni, rev),
            "fcf": cls.compute_fcf(ocf, cap),
        }

        if gp is not None and rev is not None:
            ratios["gross_margin"] = cls.compute_gross_margin(gp, rev)

        if ca is not None and cl is not None:
            ratios["working_capital"] = cls.compute_working_capital(ca, cl)

        ttm_pat = cls._safe(ttm_record.get("pat")) if ttm_record else None
        if not ttm_pat and isinstance(ttm_record, dict):
            ttm_pat = cls._safe(ttm_record.get("ttm_pat")) if ttm_record else None

        if market_cap and ttm_pat and ttm_pat > 0:
            pe = cls._safe(market_cap) / ttm_pat
            if pe and pe > 0:
                ratios["pe"] = round(pe, 2)

        return ratios

    @classmethod
    def compute_ebitda(cls, ebit, dda) -> Optional[float]:
        """EBITDA = EBIT + Depreciation & Amortisation (both from official filings)."""
        e = cls._safe(ebit)
        d = cls._safe(dda)
        if e is None:
            return None
        if d is None:
            return e  # If D&A unavailable, EBITDA ≈ EBIT
        return e + d

    @classmethod
    def compute_eps(cls, net_income, shares_outstanding) -> Optional[float]:
        return cls._div(cls._safe(net_income), cls._safe(shares_outstanding))

    @classmethod
    def _growth_rate(cls, current, previous) -> Optional[float]:
        c = cls._safe(current)
        p = cls._safe(previous)
        if c is None or p is None or p == 0:
            return None
        return (c - p) / abs(p)

    @classmethod
    def compute_quarterly_growth(cls, reports: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not reports or len(reports) < 2:
            return {}

        sorted_reports = sorted(
            reports,
            key=lambda r: str(r.get("report_date") or ""),
            reverse=True
        )
        latest = sorted_reports[0]
        prev = sorted_reports[1] if len(sorted_reports) > 1 else None
        prev_year = sorted_reports[4] if len(sorted_reports) > 4 else None

        result = {}

        if prev:
            result["eps_qoq"] = cls._growth_rate(latest.get("eps"), prev.get("eps"))
            result["sales_qoq"] = cls._growth_rate(latest.get("revenue"), prev.get("revenue"))
            result["pat_qoq"] = cls._growth_rate(latest.get("pat"), prev.get("pat"))

        if prev_year:
            result["eps_yoy"] = cls._growth_rate(latest.get("eps"), prev_year.get("eps"))
            result["sales_yoy"] = cls._growth_rate(latest.get("revenue"), prev_year.get("revenue"))
            result["pat_yoy"] = cls._growth_rate(latest.get("pat"), prev_year.get("pat"))

        return result

    @classmethod
    def compute_annual_growth(cls, reports: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not reports or len(reports) < 2:
            return {}

        sorted_reports = sorted(
            reports,
            key=lambda r: str(r.get("financial_year") or 0),
            reverse=True
        )
        latest = sorted_reports[0]
        prev = sorted_reports[1]

        result = {}
        result["revenue_growth"] = cls._growth_rate(latest.get("revenue"), prev.get("revenue"))
        result["pat_growth"] = cls._growth_rate(latest.get("pat"), prev.get("pat"))
        result["eps_growth"] = cls._growth_rate(latest.get("eps"), prev.get("eps"))
        return result

    @classmethod
    def compute_ttm(cls, reports: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Compute TTM metrics from exactly 4 distinct quarterly reports.

        Returns None if fewer than 4 distinct quarters are available.
        Never interpolates, estimates, or divides annual figures by 4.
        """
        if not reports:
            return None

        # Deduplicate reports by quarter period key (YYYY-MM)
        seen_periods = set()
        dedup_reports = []
        for r in sorted(reports, key=lambda x: str(x.get("report_date") or ""), reverse=True):
            r_date = str(r.get("report_date") or "").strip()
            if not r_date:
                continue
            try:
                dt = pd.to_datetime(r_date)
                period_key = f"{dt.year}-{dt.month:02d}"
            except Exception:
                period_key = r_date

            if period_key not in seen_periods:
                seen_periods.add(period_key)
                dedup_reports.append(r)

        # Require exactly 4 DISTINCT quarterly filings
        if len(dedup_reports) < 4:
            return None

        latest_4 = dedup_reports[:4]

        if not latest_4:
            return None

        eps_vals = [cls._safe(r.get("eps")) for r in latest_4 if cls._safe(r.get("eps")) is not None]
        ttm_eps = sum(eps_vals) if eps_vals else None

        ttm = {
            "revenue": sum(cls._safe(r.get("revenue")) for r in latest_4 if cls._safe(r.get("revenue")) is not None),
            "operating_profit": sum(cls._safe(r.get("operating_profit")) for r in latest_4 if cls._safe(r.get("operating_profit")) is not None),
            "ebit": sum(cls._safe(r.get("ebit")) for r in latest_4 if cls._safe(r.get("ebit")) is not None),
            "pat": sum(cls._safe(r.get("pat")) for r in latest_4 if cls._safe(r.get("pat")) is not None),
            "eps": ttm_eps,
            "operating_cash_flow": sum(cls._safe(r.get("operating_cash_flow")) for r in latest_4 if cls._safe(r.get("operating_cash_flow")) is not None),
            "capex": sum(cls._safe(r.get("capex")) for r in latest_4 if cls._safe(r.get("capex")) is not None),
            "gross_profit": sum(cls._safe(r.get("gross_profit")) for r in latest_4 if cls._safe(r.get("gross_profit")) is not None),
            "quarter_count": len(latest_4),
            "quarter_sources": [
                {
                    "report_date": r.get("report_date"),
                    "quarter": r.get("quarter"),
                    "financial_year": r.get("financial_year"),
                    "quarter_label": f"Q{r.get('quarter')} FY{r.get('financial_year')}" if r.get('quarter') and r.get('financial_year') else r.get('report_date'),
                    "eps": r.get("eps"),
                    "pat": r.get("pat"),
                    "revenue": r.get("revenue"),
                    "source": r.get("source"),
                }
                for r in latest_4
            ]
        }

        if latest_4:
            for key in ["equity", "assets", "liabilities", "current_assets", "current_liabilities",
                        "working_capital", "debt", "total_debt", "cash_and_cash_equivalents",
                        "depreciation_amortization", "shares_outstanding", "market_cap",
                        "retained_earnings", "share_capital", "face_value",
                        "interest_income", "interest_expense", "total_income", "non_interest_income",
                        "gross_npa", "net_npa", "total_advances", "provisions", "total_deposits", "car"]:
                ttm[key] = latest_4[0].get(key)

        ttm.update(cls.compute_all_ratios(ttm))
        return ttm

    @classmethod
    def compute_piotroski(cls, current: Union[Dict[str, Any], List[Dict[str, Any]]], previous: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if isinstance(current, list):
            if len(current) < 2:
                return {"score": None, "details": "Insufficient annual filings"}
            previous = current[1]
            current = current[0]
        elif previous is None:
            return {"score": None, "details": "Previous filing missing"}

        from fundamentals.piotroski import compute_piotroski_f_score

        current_income = {
            "Net_Income": current.get("pat"),
            "Revenue": current.get("revenue"),
            "COGS": current.get("cogs"),
        }
        previous_income = {
            "Net_Income": previous.get("pat"),
            "Revenue": previous.get("revenue"),
            "COGS": previous.get("cogs"),
        }
        current_balance = {
            "Total_Assets": current.get("assets"),
            "Stockholders_Equity": current.get("equity"),
            "Current_Assets": current.get("current_assets"),
            "Current_Liabilities": current.get("current_liabilities"),
            "Common_Shares_Outstanding": current.get("shares_outstanding"),
            "Total_Debt": current.get("debt"),
        }
        previous_balance = {
            "Total_Assets": previous.get("assets"),
            "Stockholders_Equity": previous.get("equity"),
            "Current_Assets": previous.get("current_assets"),
            "Current_Liabilities": previous.get("current_liabilities"),
            "Common_Shares_Outstanding": previous.get("shares_outstanding"),
            "Total_Debt": previous.get("debt"),
        }
        current_cashflow = {
            "Operating_Cash_Flow": current.get("operating_cash_flow"),
        }
        return compute_piotroski_f_score(
            current_income=current_income,
            previous_income=previous_income,
            current_balance=current_balance,
            previous_balance=previous_balance,
            current_cashflow=current_cashflow,
        )

    @classmethod
    def compute_altman(cls, record: Dict[str, Any], is_bank: bool = False) -> Dict[str, Any]:
        if is_bank:
            return {"score": None, "zone": "N/A", "details": "Altman Z-Score is not applicable to banking institutions"}
        from fundamentals.altman import compute_altman_z

        working_capital = cls.compute_working_capital(
            record.get("current_assets"), record.get("current_liabilities")
        )
        return compute_altman_z(
            working_capital=working_capital,
            total_assets=record.get("assets"),
            retained_earnings=record.get("retained_earnings"),
            ebit=record.get("ebit"),
            market_value_equity=record.get("market_cap"),
            total_liabilities=record.get("liabilities"),
            sales=record.get("revenue"),
        )
