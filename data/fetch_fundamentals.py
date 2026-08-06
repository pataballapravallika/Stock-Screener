from typing import Dict, Any, List
import pandas as pd
from data.providers.yfinance_provider import YahooFinanceProvider
from fundamentals.ratios import compute_roe, compute_roa, compute_debt_equity


def _safe_div(numerator, denominator):
    try:
        if numerator is None or denominator is None or denominator == 0:
            return None
        return float(numerator) / float(denominator)
    except Exception:
        return None


def _safe_float(value):
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _find_first_index(df: pd.DataFrame, candidates: List[str]) -> Any:
    for label in candidates:
        if label in df.index:
            return label
    return None


def _annual_statement_value(df: pd.DataFrame, labels: List[str]) -> Any:
    if df is None or df.empty:
        return None
    latest = df.columns[0]
    label = _find_first_index(df, labels)
    if label is None or latest not in df.columns:
        return None
    return _safe_float(df.loc[label, latest])


def _validate_against_annual(
    info_value: Any,
    annual_value: Any,
    tolerance_pct: float = 0.30,
) -> Any:
    if info_value is None and annual_value is None:
        return None
    if info_value is None:
        return annual_value
    if annual_value is None:
        return info_value
    try:
        iv = float(info_value)
        av = float(annual_value)
        if iv == 0 and av == 0:
            return iv
        if iv == 0 or av == 0:
            return av if abs(av) > abs(iv) else iv
        diff_pct = abs(iv - av) / max(abs(iv), abs(av))
        if diff_pct > tolerance_pct:
            return av
        return iv
    except Exception:
        return info_value


_provider = YahooFinanceProvider()


def _quarterly_ratios(q_income: pd.DataFrame, q_balance: pd.DataFrame) -> dict:
    result = {"quarterly_roe": {}, "quarterly_roa": {}, "quarterly_debt_equity": {}}
    if q_income is None or q_income.empty:
        return result

    ni_label = None
    for lbl in ["Net Income", "Net Income Common Stockholders", "Net Income Available to Common Shareholders"]:
        if lbl in q_income.index:
            ni_label = lbl
            break
    if ni_label is None:
        return result

    eq_label = None
    for lbl in ["Stockholders Equity", "Total Stockholder Equity", "Total Equity", "Equity"]:
        if q_balance is not None and not q_balance.empty and lbl in q_balance.index:
            eq_label = lbl
            break

    ta_label = None
    for lbl in ["Total Assets", "Assets"]:
        if q_balance is not None and not q_balance.empty and lbl in q_balance.index:
            ta_label = lbl
            break

    td_label = None
    for lbl in ["Total Debt", "Long Term Debt", "Short Term Debt"]:
        if q_balance is not None and not q_balance.empty and lbl in q_balance.index:
            td_label = lbl
            break

    for period in q_income.columns:
        ni = _safe_float(q_income.loc[ni_label, period]) if period in q_income.columns else None
        eq = None
        ta = None
        td = None
        if q_balance is not None and not q_balance.empty and period in q_balance.columns:
            if eq_label:
                eq = _safe_float(q_balance.loc[eq_label, period])
            if ta_label:
                ta = _safe_float(q_balance.loc[ta_label, period])
            if td_label:
                td = _safe_float(q_balance.loc[td_label, period])

        p_key = str(period)
        result["quarterly_roe"][p_key] = compute_roe(ni, eq)
        result["quarterly_roa"][p_key] = compute_roa(ni, ta)
        result["quarterly_debt_equity"][p_key] = compute_debt_equity(td, eq)

    return result


def fetch_fundamentals(symbol: str) -> Dict[str, Any]:
    """Fetch fundamentals via the configured provider.

    Returns a compatibility dict with legacy keys while adding richer
    fields under `quarterly_financials` and `fundamentals_source`.
    """
    try:
        info = _provider.get_info(symbol) or {}

        # preserve old-style keys for compatibility
        total_assets = info.get("totalAssets")
        total_debt = info.get("totalDebt")
        net_income = info.get("netIncome")
        ebit = info.get("ebit")
        book_value = info.get("bookValue")
        shares_outstanding = info.get("sharesOutstanding")
        current_liabilities = info.get("totalCurrentLiabilities")

        roe = info.get("returnOnEquity")
        roce = info.get("returnOnCapitalEmployed")
        roa = info.get("returnOnAssets")

        # Try to locate an explicit shareholders' equity value from common keys
        shareholders_equity = (
            info.get("totalStockholderEquity")
            or info.get("totalStockholdersEquity")
            or info.get("stockholdersEquity")
        )
        if shareholders_equity is None and book_value is not None and shares_outstanding is not None:
            try:
                shareholders_equity = float(book_value) * float(shares_outstanding)
            except Exception:
                shareholders_equity = None

        # Raw annual statement fallback values
        annual_income = _provider.get_annual_financials(symbol)
        annual_balance_sheet = _provider.get_balance_sheet(symbol)
        annual_cashflow = _provider.get_cashflow(symbol)

        if annual_balance_sheet is not None:
            bs_se = shareholders_equity or _annual_statement_value(
                annual_balance_sheet,
                [
                    "Total Stockholder Equity",
                    "Total Stockholders Equity",
                    "Stockholders Equity",
                    "Total Equity",
                    "Total Shareholders' Equity",
                    "Total Shareholders Equity",
                ],
            )
            if bs_se is not None:
                shareholders_equity = bs_se
            bs_ta = total_assets or _annual_statement_value(
                annual_balance_sheet,
                ["Total Assets", "Assets"],
            )
            if bs_ta is not None:
                total_assets = bs_ta
            bs_td = total_debt or _annual_statement_value(
                annual_balance_sheet,
                ["Total Debt", "Long Term Debt", "Short Term Debt", "Total Liab"],
            )
            if bs_td is not None:
                total_debt = bs_td

        if annual_income is not None:
            ni_annual = _annual_statement_value(
                annual_income,
                [
                    "Net Income",
                    "Net Income Common Stockholders",
                    "Net Income Available to Common Shareholders",
                    "Net Income Applicable To Common Shares",
                ],
            )
            if ni_annual is not None:
                net_income = ni_annual
            ebit_annual = _annual_statement_value(
                annual_income,
                ["EBIT", "Operating Income", "Operating Profit"],
            )
            if ebit_annual is not None:
                ebit = ebit_annual

        if roe is None and net_income is not None and shareholders_equity is not None and shareholders_equity != 0:
            roe = _safe_div(net_income, shareholders_equity)

        # ROCE = EBIT / (Total Assets - Current Liabilities)
        if roce is None and ebit is not None and total_assets is not None:
            cl = current_liabilities
            if cl is None and annual_balance_sheet is not None:
                cl = _annual_statement_value(
                    annual_balance_sheet,
                    ["Current Liabilities", "Total Current Liabilities"],
                )
            capital_employed = total_assets - cl if cl is not None else None
            if capital_employed is not None and capital_employed != 0:
                roce = _safe_div(ebit, capital_employed)

        if roa is None and net_income is not None and total_assets is not None and total_assets != 0:
            roa = _safe_div(net_income, total_assets)

        roe = _validate_against_annual(info.get("returnOnEquity"), roe)
        roce = _validate_against_annual(info.get("returnOnCapitalEmployed"), roce)
        roa = _validate_against_annual(info.get("returnOnAssets"), roa)

        operating_cash_flow_ttm = info.get("operatingCashflow")
        operating_cash_flow_annual = None
        if annual_cashflow is not None:
            operating_cash_flow_annual = _annual_statement_value(
                annual_cashflow,
                ["Operating Cash Flow", "Net Cash from Operating Activities"],
            )

        if operating_cash_flow_ttm is not None and operating_cash_flow_annual is not None:
            if abs(operating_cash_flow_ttm - operating_cash_flow_annual) > max(abs(operating_cash_flow_ttm), abs(operating_cash_flow_annual)) * 0.5:
                operating_cash_flow = operating_cash_flow_annual
            else:
                operating_cash_flow = operating_cash_flow_ttm
        else:
            operating_cash_flow = operating_cash_flow_ttm or operating_cash_flow_annual

        operating_cash_flow = _validate_against_annual(operating_cash_flow_ttm, operating_cash_flow_annual)

        free_cash_flow_annual = None
        if annual_cashflow is not None and operating_cash_flow_annual is not None:
            capex = _annual_statement_value(
                annual_cashflow,
                ["Capital Expenditures", "CapEx", "Capital Expenditure"],
            )
            if capex is not None:
                free_cash_flow_annual = _safe_float(operating_cash_flow_annual + capex)

        free_cash_flow_ttm = info.get("freeCashFlow")
        free_cash_flow = free_cash_flow_ttm or free_cash_flow_annual
        free_cash_flow = _validate_against_annual(free_cash_flow_ttm, free_cash_flow_annual)

        # Attach quarterly financials (DataFrame) and metadata when available
        q_fin = _provider.get_quarterly_financials(symbol)
        q_balance = _provider.get_quarterly_balance_sheet(symbol)
        quarterly_meta = None
        if q_fin is not None:
            periods = []
            try:
                periods = [pd for pd in q_fin.columns]
            except Exception:
                periods = list(q_fin.columns)
            quarterly_meta = {"source": "yfinance", "periods": periods}

        q_ratios = _quarterly_ratios(q_fin, q_balance)

        result = {
            "Symbol": symbol,
            "Company": info.get("longName"),
            "Sector": info.get("sector"),
            "Industry": info.get("industry"),
            "MarketCap": info.get("marketCap"),
            "PE": info.get("trailingPE"),
            "ForwardPE": info.get("forwardPE"),
            "PriceSales": info.get("priceToSalesTrailing12Months"),
            "ROE": roe,
            "ROCE": roce,
            "ROA": roa,
            "RevenueGrowth": info.get("revenueGrowth"),
            "EarningsGrowth": info.get("earningsGrowth"),
            "EarningsQuarterlyGrowth": info.get("earningsQuarterlyGrowth"),
            "DebtEquity": info.get("debtToEquity"),
            "ProfitMargin": info.get("profitMargins"),
            "DividendYield": info.get("dividendYield"),
            "NetIncome": net_income,
            "TotalAssets": total_assets,
            "TotalDebt": total_debt,
            "OperatingCashFlow": operating_cash_flow,
            "OperatingCashFlowTTM": operating_cash_flow_ttm,
            "OperatingCashFlowAnnual": operating_cash_flow_annual,
            "FreeCashFlow": free_cash_flow,
            "FreeCashFlowTTM": free_cash_flow_ttm,
            "FreeCashFlowAnnual": free_cash_flow_annual,
            "GrossMargins": info.get("grossMargins"),
            "EBIT": ebit,
            "CurrentRatio": info.get("currentRatio"),
            "QuickRatio": info.get("quickRatio"),
            "BookValue": info.get("bookValue"),
            "SharesOutstanding": shares_outstanding,
            "FloatShares": info.get("floatShares"),
            "InstitutionsPercentHeld": info.get("institutionsPercentHeld"),
            "InsidersPercentHeld": info.get("insidersPercentHeld"),
            "SharesShort": info.get("sharesShort"),
            "SharesShortPriorMonth": info.get("sharesShortPriorMonth"),
            "TotalCash": info.get("totalCash") or info.get("cash"),
            "EnterpriseValue": info.get("enterpriseValue"),
            # new additions
            "quarterly_financials": q_fin,
            "quarterly_meta": quarterly_meta,
            "quarterly_roe": q_ratios.get("quarterly_roe"),
            "quarterly_roa": q_ratios.get("quarterly_roa"),
            "quarterly_debt_equity": q_ratios.get("quarterly_debt_equity"),
            "fundamentals_source": "yfinance",
        }

        return result

    except Exception as e:
        print(f"Fundamental error {symbol}: {e}")
        return {}
