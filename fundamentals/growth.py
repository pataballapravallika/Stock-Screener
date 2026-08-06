import pandas as pd
import numpy as np
from fundamentals.ratios import (
    compute_roe,
    compute_roa,
    compute_roce,
    compute_debt_equity,
    compute_opm,
    compute_npm,
    compute_eps,
    qoq_growth,
    yoy_growth,
)
from data.fetch_utils import is_quarterly_periods


def safe_float(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def calculate_growth_metrics(income_stmt: pd.DataFrame, quarterly: bool = True) -> dict:
    if income_stmt is None or income_stmt.empty:
        return {}

    try:
        if quarterly:
            periods = list(income_stmt.columns)
            if len(periods) == 0:
                return {}

            # validate that the provided periods are quarterly-like to avoid mixing annual/TTM values
            try:
                if not is_quarterly_periods(periods):
                    return {}
            except Exception:
                pass

            latest = periods[0]
            prev = periods[1] if len(periods) > 1 else None
            prev_year = periods[4] if len(periods) > 4 else None

            revenue_col = None
            for col in ["Total Revenue", "Revenue", "Sales"]:
                if col in income_stmt.index:
                    revenue_col = col
                    break

            eps_col = None
            for col in ["Diluted EPS", "Basic EPS", "EPS"]:
                if col in income_stmt.index:
                    eps_col = col
                    break

            net_income_col = None
            for col in ["Net Income", "Net Income Common Stockholders"]:
                if col in income_stmt.index:
                    net_income_col = col
                    break

            op_income_col = None
            for col in ["Operating Income", "EBIT"]:
                if col in income_stmt.index:
                    op_income_col = col
                    break

            result = {}

            if revenue_col:
                rev_latest = safe_float(income_stmt.loc[revenue_col, latest]) if latest in income_stmt.columns else None
                result["Revenue"] = rev_latest

                if prev and prev in income_stmt.columns:
                    rev_prev = safe_float(income_stmt.loc[revenue_col, prev]) if prev in income_stmt.columns else None
                    result["Revenue_Growth_QoQ"] = qoq_growth(rev_latest, rev_prev)

                if prev_year and prev_year in income_stmt.columns:
                    rev_py = safe_float(income_stmt.loc[revenue_col, prev_year]) if prev_year in income_stmt.columns else None
                    result["Revenue_Growth_YoY"] = yoy_growth(rev_latest, rev_py)

            if eps_col:
                eps_latest = safe_float(income_stmt.loc[eps_col, latest]) if latest in income_stmt.columns else None
                result["EPS"] = eps_latest

                if prev and prev in income_stmt.columns:
                    eps_prev = safe_float(income_stmt.loc[eps_col, prev]) if prev in income_stmt.columns else None
                    result["EPS_Growth_QoQ"] = qoq_growth(eps_latest, eps_prev)

                if prev_year and prev_year in income_stmt.columns:
                    eps_py = safe_float(income_stmt.loc[eps_col, prev_year]) if prev_year in income_stmt.columns else None
                    result["EPS_Growth_YoY"] = yoy_growth(eps_latest, eps_py)

            if net_income_col:
                ni_latest = safe_float(income_stmt.loc[net_income_col, latest]) if latest in income_stmt.columns else None
                result["PAT"] = ni_latest

                if prev and prev in income_stmt.columns:
                    ni_prev = safe_float(income_stmt.loc[net_income_col, prev]) if prev in income_stmt.columns else None
                    result["PAT_Growth_QoQ"] = qoq_growth(ni_latest, ni_prev)

                if prev_year and prev_year in income_stmt.columns:
                    ni_py = safe_float(income_stmt.loc[net_income_col, prev_year]) if prev_year in income_stmt.columns else None
                    result["PAT_Growth_YoY"] = yoy_growth(ni_latest, ni_py)

            if op_income_col:
                oi_latest = safe_float(income_stmt.loc[op_income_col, latest]) if latest in income_stmt.columns else None
                result["Operating_Profit"] = oi_latest
                if revenue_col and rev_latest:
                    result["OPM"] = compute_opm(oi_latest, rev_latest)

            if net_income_col and revenue_col:
                ni_latest = safe_float(income_stmt.loc[net_income_col, latest]) if latest in income_stmt.columns else None
                rev_latest = safe_float(income_stmt.loc[revenue_col, latest]) if latest in income_stmt.columns else None
                if ni_latest is not None and rev_latest is not None:
                    result["NPM"] = compute_npm(ni_latest, rev_latest)

            return result

        else:
            periods = list(income_stmt.columns)
            if len(periods) == 0:
                return {}

            result = {}

            for i, period in enumerate(periods[:3]):
                year_key = f"Year_{period.year if hasattr(period, 'year') else period}"

                revenue_col = None
                for col in ["Total Revenue", "Revenue", "Sales"]:
                    if col in income_stmt.index:
                        revenue_col = col
                        break

                net_income_col = None
                for col in ["Net Income", "Net Income Common Stockholders"]:
                    if col in income_stmt.index:
                        net_income_col = col
                        break

                if revenue_col:
                    rev = safe_float(income_stmt.loc[revenue_col, period]) if period in income_stmt.columns else None
                    result[f"{year_key}_Revenue"] = rev

                    if i > 0:
                        prev_period = periods[i - 1]
                        prev_rev = safe_float(income_stmt.loc[revenue_col, prev_period]) if prev_period in income_stmt.columns else None
                        if rev is not None and prev_rev is not None and prev_rev != 0:
                            result[f"{year_key}_Revenue_Growth"] = (rev - prev_rev) / abs(prev_rev)

                if net_income_col:
                    ni = safe_float(income_stmt.loc[net_income_col, period]) if period in income_stmt.columns else None
                    result[f"{year_key}_PAT"] = ni

                    if i > 0:
                        prev_period = periods[i - 1]
                        prev_ni = safe_float(income_stmt.loc[net_income_col, prev_period]) if prev_period in income_stmt.columns else None
                        if ni is not None and prev_ni is not None and prev_ni != 0:
                            result[f"{year_key}_PAT_Growth"] = (ni - prev_ni) / abs(prev_ni)

                    if revenue_col and rev is not None and rev != 0:
                        result[f"{year_key}_NPM"] = ni / rev

            return result

    except Exception:
        return {}


def calculate_balance_sheet_ratios(balance_sheet: pd.DataFrame) -> dict:
    if balance_sheet is None or balance_sheet.empty:
        return {}

    try:
        periods = list(balance_sheet.columns)
        if len(periods) == 0:
            return {}

        latest = periods[0]
        result = {}

        equity_col = None
        for col in ["Stockholders Equity", "Total Equity", "Equity"]:
            if col in balance_sheet.index:
                equity_col = col
                break

        debt_col = None
        for col in ["Total Debt", "Long Term Debt", "Short Term Debt"]:
            if col in balance_sheet.index:
                debt_col = col
                break

        assets_col = None
        for col in ["Total Assets", "Assets"]:
            if col in balance_sheet.index:
                assets_col = col
                break

        if equity_col:
            eq = safe_float(balance_sheet.loc[equity_col, latest]) if latest in balance_sheet.columns else None
            result["Shareholders_Equity"] = eq

        if debt_col and equity_col:
            debt = safe_float(balance_sheet.loc[debt_col, latest]) if latest in balance_sheet.columns else None
            eq = safe_float(balance_sheet.loc[equity_col, latest]) if latest in balance_sheet.columns else None
            if debt is not None and eq is not None:
                result["Debt_Equity"] = debt / eq

        if assets_col and equity_col:
            ta = safe_float(balance_sheet.loc[assets_col, latest]) if latest in balance_sheet.columns else None
            eq = safe_float(balance_sheet.loc[equity_col, latest]) if latest in balance_sheet.columns else None
            if ta is not None and eq is not None and ta != 0:
                result["ROA"] = None

        return result

    except Exception:
        return {}


def calculate_cashflow_ratios(cashflow: pd.DataFrame) -> dict:
    if cashflow is None or cashflow.empty:
        return {}

    try:
        periods = list(cashflow.columns)
        if len(periods) == 0:
            return {}

        latest = periods[0]
        result = {}

        ocf_col = None
        for col in ["Operating Cash Flow", "Net Cash from Operating Activities"]:
            if col in cashflow.index:
                ocf_col = col
                break

        if ocf_col:
            ocf = safe_float(cashflow.loc[ocf_col, latest]) if latest in cashflow.columns else None
            result["Operating_Cash_Flow"] = ocf

        return result

    except Exception:
        return {}
