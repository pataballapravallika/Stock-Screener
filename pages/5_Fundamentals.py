import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from data.fetch_fundamentals import fetch_fundamentals
from data.fetch_prices import fetch_prices
from scoring.config import DEFAULT_CONFIG
from scoring.fundamental_score import score_fundamental, safe_float
from scoring.banking_score import score_banking
from scoring.combined_score import combined_score
from fundamentals.altman import compute_altman_z
from fundamentals.piotroski import compute_piotroski_f_score
from fundamentals.growth import calculate_growth_metrics
from fundamentals.banking import compute_banking_metrics
from scoring.technical_score import compute_technical_indicators, score_technical


st.title("Fundamental Analysis")
st.caption("Quarterly fundamentals, annual trends, and banking metrics where available")

BANK_SECTORS = {"Financial Services", "Banking", "Finance", "Insurance"}

COMPANIES = {
    "Reliance Industries": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "Infosys": "INFY.NS",
    "HDFC Bank": "HDFCBANK.NS",
    "ICICI Bank": "ICICIBANK.NS",
    "SBI": "SBIN.NS",
    "Tata Motors": "TATAMOTORS.NS",
    "ITC": "ITC.NS",
    "Wipro": "WIPRO.NS",
    "HCL Technologies": "HCLTECH.NS",
}

company = st.selectbox("Company", list(COMPANIES.keys()))
symbol = COMPANIES[company]

if st.button("Load Fundamentals", type="primary"):
    with st.spinner("Fetching company fundamentals..."):
        fund = fetch_fundamentals(symbol)

    if not fund:
        st.error("Unable to retrieve fundamentals for this ticker.")
        st.stop()

    sector = fund.get("Sector") or ""
    is_bank = any(b.lower() in sector.lower() for b in BANK_SECTORS)

    st.subheader(f"{fund.get('Company') or symbol}")
    st.caption(f"Sector: {sector or 'N/A'} | Symbol: {symbol}")

    df_prices = fetch_prices(symbol, period="1y")
    tech_result = {}
    if not df_prices.empty:
        df_ind = compute_technical_indicators(df_prices)
        latest = df_ind.iloc[-1]
        tech_result = score_technical(latest)

    fund_for_scoring = {
        "EPS_Growth": fund.get("EarningsGrowth"),
        "Revenue_Growth": fund.get("RevenueGrowth"),
        "PAT_Growth": fund.get("PAT_Growth"),
        "ROE": fund.get("ROE"),
        "ROCE": fund.get("ROCE"),
        "ROA": fund.get("ROA"),
        "Debt_Equity": fund.get("DebtEquity"),
    }

    fund_score_result = score_fundamental(fund_for_scoring)
    combined = combined_score(
        technical_result=tech_result,
        fundamental_result=fund_score_result,
        is_bank=is_bank,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Technical Score", f"{tech_result.get('percentage', 0):.0f}%", tech_result.get("signal", "N/A"))
    c2.metric("Fundamental Score", f"{fund_score_result.get('percentage', 0):.0f}%", fund_score_result.get("signal", "N/A"))
    c3.metric("Combined Score", f"{combined.get('combined_percentage', 0):.0f}%", combined.get("combined_signal", "N/A"))
    c4.metric("Signal", combined.get("combined_signal", "N/A"))

    st.divider()
    st.subheader("Key Metrics")
    key_metrics = pd.DataFrame({
        "Metric": [
            "Market Cap", "Trailing P/E", "Forward P/E", "Price / Sales",
            "ROE", "ROCE", "ROA", "Debt / Equity", "Profit Margin",
            "Dividend Yield", "Revenue Growth", "Earnings Growth",
        ],
        "Value": [
            fund.get("MarketCap"),
            fund.get("PE"),
            fund.get("ForwardPE"),
            fund.get("PriceSales"),
            fund.get("ROE"),
            fund.get("ROCE"),
            fund.get("ROA"),
            fund.get("DebtEquity"),
            fund.get("ProfitMargin"),
            fund.get("DividendYield"),
            fund.get("RevenueGrowth"),
            fund.get("EarningsGrowth"),
        ]
    })

    def fmt_metric(val, fmt):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return "N/A"
        return fmt(val)

    display_metrics = pd.DataFrame({
        "Metric": key_metrics["Metric"],
        "Value": [
            fmt_metric(fund.get("MarketCap"), lambda v: f"${v/1e9:.2f}B" if v > 1e9 else f"${v/1e6:.2f}M"),
            fmt_metric(fund.get("PE"), lambda v: f"{v:.2f}"),
            fmt_metric(fund.get("ForwardPE"), lambda v: f"{v:.2f}"),
            fmt_metric(fund.get("PriceSales"), lambda v: f"{v:.2f}"),
            fmt_metric(fund.get("ROE"), lambda v: f"{v*100:.2f}%"),
            fmt_metric(fund.get("ROCE"), lambda v: f"{v*100:.2f}%"),
            fmt_metric(fund.get("ROA"), lambda v: f"{v*100:.2f}%"),
            fmt_metric(fund.get("DebtEquity"), lambda v: f"{v:.2f}"),
            fmt_metric(fund.get("ProfitMargin"), lambda v: f"{v*100:.2f}%"),
            fmt_metric(fund.get("DividendYield"), lambda v: f"{v*100:.2f}%"),
            fmt_metric(fund.get("RevenueGrowth"), lambda v: f"{v*100:.2f}%"),
            fmt_metric(fund.get("EarningsGrowth"), lambda v: f"{v*100:.2f}%"),
        ]
    })
    st.dataframe(display_metrics, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Annual Fundamentals")

    try:
        ticker = yf.Ticker(symbol)
        income_stmt = ticker.income_stmt
        balance_sheet = ticker.balance_sheet
        cashflow = ticker.cashflow
    except Exception as e:
        st.warning(f"Could not retrieve financial statements: {e}")
        income_stmt = None
        balance_sheet = None
        cashflow = None

    annual_growth = {}
    if income_stmt is not None and not income_stmt.empty:
        annual_growth = calculate_growth_metrics(income_stmt, quarterly=False)

    if annual_growth:
        annual_rows = []
        for key in sorted(annual_growth.keys()):
            val = annual_growth[key]
            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                annual_rows.append({"Metric": key, "Value": f"{val:.4f}" if isinstance(val, float) else str(val)})
        if annual_rows:
            st.dataframe(pd.DataFrame(annual_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Annual fundamentals unavailable from current data provider.")

    st.divider()
    st.subheader("Quarterly Fundamentals")

    quarterly_growth = {}
    if income_stmt is not None and not income_stmt.empty:
        quarterly_growth = calculate_growth_metrics(income_stmt, quarterly=True)

    if quarterly_growth:
        q_rows = []
        for key in sorted(quarterly_growth.keys()):
            val = quarterly_growth[key]
            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                display = f"{val*100:.2f}%" if isinstance(val, float) and abs(val) < 10 else f"{val:.4f}"
                q_rows.append({"Metric": key, "Value": display})
        if q_rows:
            st.dataframe(pd.DataFrame(q_rows), use_container_width=True, hide_index=True)
        else:
            st.info("Quarterly growth data unavailable.")
    else:
        st.info("Quarterly fundamentals unavailable from current data provider.")

    st.divider()
    st.subheader("Altman Z-Score")
    try:
        if balance_sheet is not None and not balance_sheet.empty:
            periods = list(balance_sheet.columns)
            latest_period = periods[0] if periods else None
            if latest_period:
                def _get_bs(label):
                    try:
                        if label in balance_sheet.index and latest_period in balance_sheet.columns:
                            return safe_float(balance_sheet.loc[label, latest_period])
                    except Exception:
                        pass
                    return None

                wc = _get_bs("Working Capital") or _get_bs("Current Assets") - _get_bs("Current Liabilities") if _get_bs("Current Assets") is not None and _get_bs("Current Liabilities") is not None else None
                ta = _get_bs("Total Assets")
                re = _get_bs("Retained Earnings") or _get_bs("Stockholders Equity")
                ebit = _get_bs("EBIT")
                mve = _get_bs("Market Cap") or _get_bs("Market Cap")
                tl = _get_bs("Total Liabilities Net Minority Interest") or _get_bs("Total Debt")
                sales = None
                if income_stmt is not None and not income_stmt.empty:
                    try:
                        sales = safe_float(income_stmt.loc["Total Revenue", latest_period])
                    except Exception:
                        pass

                altman = compute_altman_z(wc, ta, re, ebit, mve, tl, sales)
                st.write(f"**Z-Score:** {altman.get('value', 'N/A')} | **Status:** {altman.get('status', 'N/A')}")
                st.caption(altman.get("formula", ""))
            else:
                st.info("Insufficient balance sheet data for Altman Z-Score.")
        else:
            st.info("Balance sheet data unavailable for Altman Z-Score.")
    except Exception as e:
        st.info(f"Altman Z-Score unavailable: {e}")

    st.divider()
    st.subheader("Piotroski F-Score")
    try:
        if balance_sheet is not None and not balance_sheet.empty and cashflow is not None and not cashflow.empty:
            periods_bs = list(balance_sheet.columns)
            periods_cf = list(cashflow.columns)
            latest_bs = periods_bs[0] if periods_bs else None
            prev_bs = periods_bs[1] if len(periods_bs) > 1 else None
            latest_cf = periods_cf[0] if periods_cf else None
            prev_cf = periods_cf[1] if len(periods_cf) > 1 else None

            def _get_bs_val(label):
                try:
                    if latest_bs is not None and label in balance_sheet.index and latest_bs in balance_sheet.columns:
                        return safe_float(balance_sheet.loc[label, latest_bs])
                except Exception:
                    pass
                return None

            def _get_bs_val_prev(label):
                try:
                    if prev_bs is not None and label in balance_sheet.index and prev_bs in balance_sheet.columns:
                        return safe_float(balance_sheet.loc[label, prev_bs])
                except Exception:
                    pass
                return None

            def _get_cf_val(label):
                try:
                    if latest_cf is not None and label in cashflow.index and latest_cf in cashflow.columns:
                        return safe_float(cashflow.loc[label, latest_cf])
                except Exception:
                    pass
                return None

            current_income = {
                "Net_Income": _get_bs_val("Net Income") or fund.get("NetIncome"),
                "Revenue": _get_bs_val("Total Revenue"),
                "Total_Assets": _get_bs_val("Total Assets"),
            }
            previous_income = {
                "Net_Income": _get_bs_val_prev("Net Income"),
                "Revenue": _get_bs_val_prev("Total Revenue"),
                "Total_Assets": _get_bs_val_prev("Total Assets"),
            }
            current_balance = {
                "Total_Assets": _get_bs_val("Total Assets"),
                "Total_Debt": _get_bs_val("Total Debt") or _get_bs_val("Long Term Debt"),
                "Stockholders_Equity": _get_bs_val("Stockholders Equity"),
                "Current_Assets": _get_bs_val("Current Assets"),
                "Current_Liabilities": _get_bs_val("Current Liabilities"),
                "Common_Shares_Outstanding": _get_bs_val("Common Stock") or _get_bs_val("Ordinary Shares Number"),
            }
            previous_balance = {
                "Total_Assets": _get_bs_val_prev("Total Assets"),
                "Total_Debt": _get_bs_val_prev("Total Debt") or _get_bs_val_prev("Long Term Debt"),
                "Stockholders_Equity": _get_bs_val_prev("Stockholders Equity"),
                "Current_Assets": _get_bs_val_prev("Current Assets"),
                "Current_Liabilities": _get_bs_val_prev("Current Liabilities"),
                "Common_Shares_Outstanding": _get_bs_val_prev("Common Stock") or _get_bs_val_prev("Ordinary Shares Number"),
            }
            current_cashflow = {
                "Operating_Cash_Flow": _get_cf_val("Operating Cash Flow") or _get_cf_val("Net Cash from Operating Activities"),
            }

            piotroski = compute_piotroski_f_score(
                current_income,
                previous_income,
                current_balance,
                previous_balance,
                current_cashflow,
            )
            st.write(f"**Score:** {piotroski.get('score', 'N/A')} / 9")
            if piotroski.get("missing"):
                st.caption(f"Signals unavailable: {', '.join(piotroski['missing'])}")
        else:
            st.info("Insufficient data for Piotroski F-Score.")
    except Exception as e:
        st.info(f"Piotroski F-Score unavailable: {e}")

    if is_bank:
        st.divider()
        st.subheader("Banking Fundamentals")
        try:
            banking_data = {
                "NIM": fund.get("NIM"),
                "NII": fund.get("NII"),
                "CASA_Ratio": fund.get("CASA_Ratio"),
                "GNPA": fund.get("GNPA"),
                "NNPA": fund.get("NNPA"),
                "PCR": fund.get("PCR"),
                "Advances_Growth": fund.get("Advances_Growth"),
                "Deposits_Growth": fund.get("Deposits_Growth"),
                "CAR": fund.get("CAR"),
                "ROA": fund.get("ROA"),
                "ROE": fund.get("ROE"),
            }
            bank_result = compute_banking_metrics(banking_data, {})
            bank_score = score_banking(banking_data)

            bank_display = pd.DataFrame({
                "Metric": [
                    "NIM", "NII", "CASA Ratio", "GNPA", "NNPA",
                    "PCR", "Advances Growth", "Deposits Growth", "CAR", "ROA", "ROE"
                ],
                "Value": [
                    f"{banking_data['NIM']:.2f}%" if banking_data.get("NIM") is not None else "Additional banking data source required",
                    f"{banking_data['NII']:.2f}" if banking_data.get("NII") is not None else "Additional banking data source required",
                    f"{banking_data['CASA_Ratio']:.2f}%" if banking_data.get("CASA_Ratio") is not None else "Additional banking data source required",
                    f"{banking_data['GNPA']:.2f}%" if banking_data.get("GNPA") is not None else "Additional banking data source required",
                    f"{banking_data['NNPA']:.2f}%" if banking_data.get("NNPA") is not None else "Additional banking data source required",
                    f"{banking_data['PCR']:.2f}%" if banking_data.get("PCR") is not None else "Additional banking data source required",
                    f"{banking_data['Advances_Growth']*100:.2f}%" if banking_data.get("Advances_Growth") is not None else "Additional banking data source required",
                    f"{banking_data['Deposits_Growth']*100:.2f}%" if banking_data.get("Deposits_Growth") is not None else "Additional banking data source required",
                    f"{banking_data['CAR']:.2f}%" if banking_data.get("CAR") is not None else "Additional banking data source required",
                    f"{banking_data['ROA']*100:.2f}%" if banking_data.get("ROA") is not None else "N/A",
                    f"{banking_data['ROE']*100:.2f}%" if banking_data.get("ROE") is not None else "N/A",
                ]
            })
            st.dataframe(bank_display, use_container_width=True, hide_index=True)
            st.write(f"**Banking Score:** {bank_score.get('percentage', 0):.0f}% | **Signal:** {bank_score.get('signal', 'N/A')}")
        except Exception as e:
            st.info(f"Banking fundamentals unavailable: {e}")

    st.divider()
    st.subheader("Shareholding Pattern")
    try:
        ticker = yf.Ticker(symbol)
        holders = ticker.major_holders
        if holders is not None and not holders.empty:
            st.dataframe(holders, use_container_width=True)
        else:
            st.info("Shareholding data unavailable from current provider.")
    except Exception:
        st.info("Shareholding data unavailable. Additional data source required.")

    st.divider()
    st.subheader("Scoring Details")
    st.json({
        "technical_score": tech_result,
        "fundamental_score": fund_score_result,
        "combined_score": combined,
        "is_bank": is_bank,
    })
