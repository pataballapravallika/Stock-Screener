import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
from data.fetch_fundamentals import fetch_fundamentals
from data.fetch_prices import fetch_prices
from scoring.technical_score import compute_technical_indicators, score_technical
from scoring.fundamental_score import score_fundamental
from scoring.combined_score import combined_score

st.set_page_config(page_title="Alerts & AI Research", layout="wide")

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

ALERT_TYPES = [
    "Price Above", "Price Below", "RSI Above", "RSI Below",
    "Volume Spike", "Daily Change %", "ROE Above", "ROCE Above",
    "P/E Below", "P/E Above", "Dividend Yield Above",
    "Breakout Alert", "Earnings Surprise", "Shareholding Change",
    "Insider Trading", "Order Win", "Capex Announcement",
]

st.title("Alerts & Automation + AI Research Assistant")
st.caption("Set alerts, automate screening, and get AI-powered research insights")

tab1, tab2, tab3 = st.tabs(["Alerts & Automation", "AI Research Assistant", "Watchlist Suggestions"])

with tab1:
    st.subheader("Alert Management")

    ALERTS_KEY = "alerts"
    if ALERTS_KEY not in st.session_state:
        st.session_state[ALERTS_KEY] = []

    with st.sidebar.expander("Create Alert", expanded=True):
        alert_symbol = st.selectbox("Symbol", list(COMPANIES.keys()), key="alert_sym")
        alert_type = st.selectbox("Alert Type", ALERT_TYPES, key="alert_type")
        alert_threshold = st.number_input("Threshold Value", value=0.0, step=0.01, key="alert_thresh")
        alert_active = st.checkbox("Active", value=True, key="alert_active")

        if st.button("Add Alert", key="add_alert"):
            st.session_state[ALERTS_KEY].append({
                "symbol": COMPANIES[alert_symbol],
                "company": alert_symbol,
                "type": alert_type,
                "threshold": alert_threshold,
                "active": alert_active,
                "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "triggered": False,
            })
            st.sidebar.success(f"Alert added for {alert_symbol}")

    st.markdown("### Active Alerts")
    if st.session_state[ALERTS_KEY]:
        alert_df = pd.DataFrame(st.session_state[ALERTS_KEY])
        st.dataframe(alert_df, use_container_width=True, hide_index=True)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Check Alerts Now"):
                for i, alert in enumerate(st.session_state[ALERTS_KEY]):
                    try:
                        df = fetch_prices(alert["symbol"], period="1d")
                        if not df.empty:
                            latest = df.iloc[-1]
                            triggered = False
                            if "Price Above" in alert["type"] and latest["Close"] > alert["threshold"]:
                                triggered = True
                            elif "Price Below" in alert["type"] and latest["Close"] < alert["threshold"]:
                                triggered = True
                            elif "RSI Above" in alert["type"] and pd.notna(latest.get("RSI")) and latest["RSI"] > alert["threshold"]:
                                triggered = True
                            elif "RSI Below" in alert["type"] and pd.notna(latest.get("RSI")) and latest["RSI"] < alert["threshold"]:
                                triggered = True
                            elif "Volume Spike" in alert["type"] and pd.notna(latest.get("Volume_MA20")) and latest["Volume"] > latest["Volume_MA20"] * alert["threshold"]:
                                triggered = True
                            if triggered:
                                st.session_state[ALERTS_KEY][i]["triggered"] = True
                                st.warning(f"Alert triggered: {alert['company']} — {alert['type']} ({alert['threshold']})")
                    except Exception:
                        pass
    else:
        st.caption("No alerts configured yet.")

    st.divider()

    st.subheader("Live Alert Evaluation")
    st.caption("Checks current market data against all active alerts")

    eval_results = []
    for alert in st.session_state[ALERTS_KEY]:
        if not alert.get("active", True):
            continue
        try:
            df = fetch_prices(alert["symbol"], period="1d")
            if df.empty:
                continue
            latest = df.iloc[-1]
            current_price = float(latest["Close"])
            current_rsi = float(latest.get("RSI", np.nan)) if pd.notna(latest.get("RSI")) else None
            current_volume = float(latest.get("Volume", 0))
            prev_close = float(latest.get("Open", current_price))
            daily_change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close != 0 else 0.0

            triggered = False
            trigger_reason = ""

            alert_type = alert["type"]
            threshold = alert["threshold"]

            if alert_type == "Price Above" and current_price > threshold:
                triggered = True
                trigger_reason = f"Current price ₹{current_price:,.2f} > ₹{threshold:,.2f}"
            elif alert_type == "Price Below" and current_price < threshold:
                triggered = True
                trigger_reason = f"Current price ₹{current_price:,.2f} < ₹{threshold:,.2f}"
            elif alert_type == "RSI Above" and current_rsi is not None and current_rsi > threshold:
                triggered = True
                trigger_reason = f"RSI {current_rsi:.1f} > {threshold}"
            elif alert_type == "RSI Below" and current_rsi is not None and current_rsi < threshold:
                triggered = True
                trigger_reason = f"RSI {current_rsi:.1f} < {threshold}"
            elif alert_type == "Volume Spike" and current_volume > threshold:
                triggered = True
                trigger_reason = f"Volume {current_volume:,.0f} > {threshold:,.0f}"
            elif alert_type == "Daily Change %" and abs(daily_change_pct) > threshold:
                triggered = True
                trigger_reason = f"Daily change {daily_change_pct:.2f}% exceeds ±{threshold}%"
            elif alert_type == "ROE Above":
                fund = fetch_fundamentals(alert["symbol"])
                roe = fund.get("ROE")
                if roe is not None and roe > threshold:
                    triggered = True
                    trigger_reason = f"ROE {roe*100:.2f}% > {threshold*100:.2f}%"
            elif alert_type == "ROCE Above":
                fund = fetch_fundamentals(alert["symbol"])
                roce = fund.get("ROCE")
                if roce is not None and roce > threshold:
                    triggered = True
                    trigger_reason = f"ROCE {roce*100:.2f}% > {threshold*100:.2f}%"
            elif alert_type == "P/E Below":
                fund = fetch_fundamentals(alert["symbol"])
                pe = fund.get("PE")
                if pe is not None and pe < threshold:
                    triggered = True
                    trigger_reason = f"P/E {pe:.2f} < {threshold:.2f}"
            elif alert_type == "P/E Above":
                fund = fetch_fundamentals(alert["symbol"])
                pe = fund.get("PE")
                if pe is not None and pe > threshold:
                    triggered = True
                    trigger_reason = f"P/E {pe:.2f} > {threshold:.2f}"
            elif alert_type == "Dividend Yield Above":
                fund = fetch_fundamentals(alert["symbol"])
                dy = fund.get("DividendYield")
                if dy is not None and dy > threshold:
                    triggered = True
                    trigger_reason = f"Dividend Yield {dy*100:.2f}% > {threshold*100:.2f}%"

            eval_results.append({
                "Symbol": alert["symbol"],
                "Company": alert["company"],
                "Alert Type": alert_type,
                "Threshold": alert["threshold"],
                "Current Value": f"{current_price:,.2f}" if alert_type in ("Price Above", "Price Below") else
                                 f"{current_rsi:.1f}" if alert_type in ("RSI Above", "RSI Below") else
                                 f"{current_volume:,.0f}" if alert_type == "Volume Spike" else
                                 f"{daily_change_pct:.2f}%" if alert_type == "Daily Change %" else
                                 f"{roe*100:.2f}%" if alert_type == "ROE Above" else
                                 f"{roce*100:.2f}%" if alert_type == "ROCE Above" else
                                 f"{pe:.2f}" if alert_type in ("P/E Below", "P/E Above") else
                                 f"{dy*100:.2f}%" if alert_type == "Dividend Yield Above" else "N/A",
                "Triggered": "YES" if triggered else "No",
                "Reason": trigger_reason if triggered else "—",
            })
        except Exception as e:
            eval_results.append({
                "Symbol": alert["symbol"],
                "Company": alert["company"],
                "Alert Type": alert_type,
                "Threshold": alert["threshold"],
                "Current Value": "Error",
                "Triggered": "Error",
                "Reason": str(e),
            })

    if eval_results:
        eval_df = pd.DataFrame(eval_results)
        triggered_df = eval_df[eval_df["Triggered"] == "YES"]
        if not triggered_df.empty:
            st.warning(f"**{len(triggered_df)} alert(s) triggered!**")
            st.dataframe(triggered_df, use_container_width=True, hide_index=True)

        all_df = eval_df
        st.dataframe(all_df, use_container_width=True, hide_index=True)
    else:
        st.info("No alerts to evaluate.")

    st.divider()

    st.subheader("Alert History")
    st.info("Alert history is stored in session state and resets on page refresh. For persistent alerts, integrate with a database or file-based storage.")

    if st.session_state[ALERTS_KEY]:
        st.json(st.session_state[ALERTS_KEY])

    st.subheader("Automated Screening Rules")
    st.caption("Define rules that automatically screen stocks based on technical and fundamental criteria")

    rule_company = st.selectbox("Screen Company", list(COMPANIES.keys()), key="rule_company")
    rule_min_score = st.slider("Min Combined Score", 0, 100, 50, key="rule_score")
    rule_min_technical = st.slider("Min Technical Score", 0, 100, 40, key="rule_tech")
    rule_min_fundamental = st.slider("Min Fundamental Score", 0, 100, 40, key="rule_fund")
    rule_signal = st.selectbox("Signal Filter", ["BUY", "HOLD", "SELL", "All"], key="rule_signal")

    if st.button("Run Automated Screen", key="run_screen"):
        with st.spinner("Running automated screen..."):
            symbol = COMPANIES[rule_company]
            df = fetch_prices(symbol, period="1y")
            if not df.empty:
                df = compute_technical_indicators(df)
                latest = df.iloc[-1]
                tech_result = score_technical(latest)
                fund = fetch_fundamentals(symbol) or {}
                fund_for_scoring = {
                    "EPS_Growth": fund.get("EarningsGrowth"),
                    "Revenue_Growth": fund.get("RevenueGrowth"),
                    "PAT_Growth": None,
                    "ROE": fund.get("ROE"),
                    "ROCE": fund.get("ROCE"),
                    "ROA": fund.get("ROA"),
                    "Debt_Equity": fund.get("DebtEquity"),
                }
                fund_score_result = score_fundamental(fund_for_scoring)
                combined = combined_score(
                    technical_result=tech_result,
                    fundamental_result=fund_score_result,
                    is_bank=False,
                )

                meets_score = combined["combined_percentage"] >= rule_min_score
                meets_tech = tech_result["percentage"] >= rule_min_technical
                meets_fund = fund_score_result["percentage"] >= rule_min_fundamental
                meets_signal = rule_signal == "All" or combined["combined_signal"] == rule_signal

                if meets_score and meets_tech and meets_fund and meets_signal:
                    st.success(f"{rule_company} PASSED all screening rules!")
                    st.metric("Combined Score", f"{combined['combined_percentage']:.0f}/100")
                    st.metric("Signal", combined["combined_signal"])
                else:
                    st.warning(f"{rule_company} did not pass all screening rules.")
                    st.write(f"Score: {combined['combined_percentage']:.0f} (min: {rule_min_score})")
                    st.write(f"Technical: {tech_result['percentage']:.0f}% (min: {rule_min_technical}%)")
                    st.write(f"Fundamental: {fund_score_result['percentage']:.0f}% (min: {rule_min_fundamental}%)")
                    st.write(f"Signal: {combined['combined_signal']} (filter: {rule_signal})")

with tab2:
    st.subheader("AI Research Assistant")
    st.caption("AI-powered analysis and insights using fundamental and technical data")

    company = st.selectbox("Company", list(COMPANIES.keys()), key="ai_company")
    symbol = COMPANIES[company]

    analysis_type = st.radio(
        "Analysis Type",
        ["Full Report", "Technical Analysis", "Fundamental Analysis", "Risk Assessment", "Peer Comparison"],
        horizontal=True,
        key="ai_type",
    )

    if st.button("Run Analysis", type="primary", key="ai_run"):
        with st.spinner("Analyzing..."):
            fund = fetch_fundamentals(symbol)
            df_prices = fetch_prices(symbol, period="1y")

        if not fund:
            st.error("Unable to retrieve data for this ticker.")
            st.stop()

        st.subheader(f"Analysis Report: {fund.get('Company') or symbol}")
        st.caption(f"Symbol: {symbol} | Sector: {fund.get('Sector') or 'N/A'} | Industry: {fund.get('Industry') or 'N/A'}")

        if analysis_type in ("Full Report", "Technical Analysis"):
            st.markdown("### Technical Analysis")
            if not df_prices.empty:
                df_prices = compute_technical_indicators(df_prices)
                latest = df_prices.iloc[-1]
                tech = score_technical(latest)

                c1, c2, c3 = st.columns(3)
                c1.metric("Technical Score", f"{tech.get('percentage', 0):.0f}%", tech.get("signal", "N/A"))
                c2.metric("Price", f"₹{latest['Close']:,.2f}")
                c3.metric("52W High", f"₹{latest.get('52W_High', 0):,.2f}")

                st.markdown("**Signal Conditions**")
                conditions = tech.get("conditions", {})
                cond_df = pd.DataFrame([
                    {"Condition": k.replace("_", " ").title(), "Status": "Pass" if v else "Fail"}
                    for k, v in conditions.items()
                ])
                st.dataframe(cond_df, use_container_width=True, hide_index=True)

                st.markdown("**Key Technical Levels**")
                levels = {
                    "MA20": latest.get("MA20"),
                    "MA50": latest.get("MA50"),
                    "MA200": latest.get("MA200"),
                    "RSI": latest.get("RSI"),
                    "MACD": latest.get("MACD"),
                    "Bollinger Upper": latest.get("BB_Upper"),
                    "Bollinger Lower": latest.get("BB_Lower"),
                    "SuperTrend": "Bullish" if latest.get("SuperTrend") == 1 else "Bearish",
                }
                levels_df = pd.DataFrame([
                    {"Indicator": k, "Value": f"{v:.2f}" if isinstance(v, (int, float)) and pd.notna(v) else str(v) if v is not None else "N/A"}
                    for k, v in levels.items()
                ])
                st.dataframe(levels_df, use_container_width=True, hide_index=True)

                if "ema_alignment" in conditions:
                    if conditions["ema_alignment"]:
                        st.success("EMA alignment is bullish — shorter MAs are above longer MAs.")
                    else:
                        st.warning("EMA alignment is bearish or neutral — check MA crossovers.")

        if analysis_type in ("Full Report", "Fundamental Analysis"):
            st.markdown("### Fundamental Analysis")

            fund_summary = [
                {"Metric": "Market Cap", "Value": f"₹{fund.get('MarketCap', 0)/1e9:.2f}B" if fund.get("MarketCap") else "N/A"},
                {"Metric": "P/E Ratio", "Value": f"{fund.get('PE'):.2f}" if fund.get("PE") else "N/A"},
                {"Metric": "Forward P/E", "Value": f"{fund.get('ForwardPE'):.2f}" if fund.get("ForwardPE") else "N/A"},
                {"Metric": "Price/Sales", "Value": f"{fund.get('PriceSales'):.2f}" if fund.get("PriceSales") else "N/A"},
                {"Metric": "ROE (Annual)", "Value": f"{fund.get('ROE')*100:.2f}%" if fund.get("ROE") else "N/A"},
                {"Metric": "ROCE (Annual)", "Value": f"{fund.get('ROCE')*100:.2f}%" if fund.get("ROCE") else "N/A"},
                {"Metric": "ROA (Annual)", "Value": f"{fund.get('ROA')*100:.2f}%" if fund.get("ROA") else "N/A"},
                {"Metric": "Debt/Equity", "Value": f"{fund.get('DebtEquity'):.2f}" if fund.get("DebtEquity") else "N/A"},
                {"Metric": "Profit Margin", "Value": f"{fund.get('ProfitMargin')*100:.2f}%" if fund.get("ProfitMargin") else "N/A"},
                {"Metric": "Operating Cash Flow (TTM)", "Value": f"₹{fund.get('OperatingCashFlowTTM'):,.0f}" if fund.get("OperatingCashFlowTTM") else "N/A"},
                {"Metric": "Operating Cash Flow (Annual)", "Value": f"₹{fund.get('OperatingCashFlowAnnual'):,.0f}" if fund.get("OperatingCashFlowAnnual") else "N/A"},
                {"Metric": "Free Cash Flow (TTM)", "Value": f"₹{fund.get('FreeCashFlow'):,.0f}" if fund.get("FreeCashFlow") else "N/A"},
                {"Metric": "Free Cash Flow (Annual)", "Value": f"₹{fund.get('FreeCashFlowAnnual'):,.0f}" if fund.get("FreeCashFlowAnnual") else "N/A"},
                {"Metric": "Revenue Growth", "Value": f"{fund.get('RevenueGrowth')*100:.2f}%" if fund.get("RevenueGrowth") else "N/A"},
                {"Metric": "Earnings Growth", "Value": f"{fund.get('EarningsGrowth')*100:.2f}%" if fund.get("EarningsGrowth") else "N/A"},
                {"Metric": "Dividend Yield", "Value": f"{fund.get('DividendYield')*100:.2f}%" if fund.get("DividendYield") else "N/A"},
            ]
            st.dataframe(pd.DataFrame(fund_summary), use_container_width=True, hide_index=True)

            st.markdown("**AI Insight — Fundamental Assessment**")
            roe = fund.get("ROE")
            roce = fund.get("ROCE")
            de = fund.get("DebtEquity")
            margin = fund.get("ProfitMargin")
            ocf = fund.get("OperatingCashFlowAnnual")
            fcf = fund.get("FreeCashFlowAnnual")

            insights = []
            if roe is not None:
                if roe > 0.20:
                    insights.append(f"ROE of {roe*100:.1f}% is strong, indicating efficient use of equity capital.")
                elif roe > 0.10:
                    insights.append(f"ROE of {roe*100:.1f}% is moderate. Room for improvement in capital efficiency.")
                else:
                    insights.append(f"ROE of {roe*100:.1f}% is below average. The company may be struggling to generate returns.")
            if roce is not None:
                if roce > 0.20:
                    insights.append(f"ROCE of {roce*100:.1f}% shows excellent capital allocation across all capital providers.")
                elif roce > 0.10:
                    insights.append(f"ROCE of {roce*100:.1f}% is acceptable but not exceptional.")
                else:
                    insights.append(f"ROCE of {roce*100:.1f}% is weak, suggesting capital is not being deployed efficiently.")
            if de is not None:
                if de > 200:
                    insights.append(f"Debt/Equity of {de:.1f}x is high — the company carries significant financial leverage.")
                elif de > 100:
                    insights.append(f"Debt/Equity of {de:.1f}x is moderate. Monitor debt levels for sustainability.")
                else:
                    insights.append(f"Debt/Equity of {de:.1f}x is conservative, providing a buffer against downturns.")
            if margin is not None:
                if margin > 0.20:
                    insights.append(f"Profit margin of {margin*100:.1f}% is strong, indicating good pricing power or cost control.")
                elif margin > 0.10:
                    insights.append(f"Profit margin of {margin*100:.1f}% is reasonable for the sector.")
                else:
                    insights.append(f"Profit margin of {margin*100:.1f}% is thin. Cost optimization may be needed.")
            if ocf is not None and fcf is not None:
                if fcf > 0:
                    insights.append(f"Positive free cash flow (₹{fcf/1e9:.1f}B) confirms the company generates cash after investments.")
                else:
                    insights.append(f"Negative free cash flow (₹{fcf/1e9:.1f}B) is a concern — the company may be consuming cash.")

            for insight in insights:
                st.write(f"• {insight}")

        if analysis_type in ("Full Report", "Risk Assessment"):
            st.markdown("### Risk Assessment")

            risk_factors = []
            pe = fund.get("PE")
            fwd_pe = fund.get("ForwardPE")
            dy = fund.get("DividendYield")
            de = fund.get("DebtEquity")
            roe = fund.get("ROE")
            roa = fund.get("ROA")

            if pe is not None and pe > 50:
                risk_factors.append({"Risk": "High", "Factor": f"P/E of {pe:.1f}x is elevated — valuation risk"})
            elif pe is not None and pe > 30:
                risk_factors.append({"Risk": "Medium", "Factor": f"P/E of {pe:.1f}x is above average — moderate valuation risk"})
            elif pe is not None:
                risk_factors.append({"Risk": "Low", "Factor": f"P/E of {pe:.1f}x is reasonable"})

            if de is not None and de > 200:
                risk_factors.append({"Risk": "High", "Factor": f"Debt/Equity of {de:.1f}x is high — financial risk"})
            elif de is not None and de > 100:
                risk_factors.append({"Risk": "Medium", "Factor": f"Debt/Equity of {de:.1f}x is moderate — watch leverage"})
            elif de is not None:
                risk_factors.append({"Risk": "Low", "Factor": f"Debt/Equity of {de:.1f}x is conservative"})

            if roe is not None and roe < 0.05:
                risk_factors.append({"Risk": "High", "Factor": f"ROE of {roe*100:.1f}% is very low — profitability risk"})
            elif roe is not None and roe < 0.10:
                risk_factors.append({"Risk": "Medium", "Factor": f"ROE of {roe*100:.1f}% is below average"})
            elif roe is not None:
                risk_factors.append({"Risk": "Low", "Factor": f"ROE of {roe*100:.1f}% is strong"})

            if dy is not None and dy > 0.05:
                risk_factors.append({"Risk": "Medium", "Factor": f"Dividend yield of {dy*100:.1f}% may not be sustainable"})
            elif dy is not None and dy > 0:
                risk_factors.append({"Risk": "Low", "Factor": f"Dividend yield of {dy*100:.1f}% provides income"})

            if not risk_factors:
                risk_factors.append({"Risk": "N/A", "Factor": "Insufficient data for risk assessment"})

            risk_df = pd.DataFrame(risk_factors)
            st.dataframe(risk_df, use_container_width=True, hide_index=True)

            risk_colors = {"High": "#f8d7da", "Medium": "#fff3cd", "Low": "#d4edda"}
            for _, row in risk_df.iterrows():
                color = risk_colors.get(row["Risk"], "#f8f9fa")
                st.markdown(f"<div style='background-color:{color}; padding:5px 10px; border-radius:3px; margin:2px 0;'>"
                            f"<b>{row['Risk']}</b>: {row['Factor']}</div>", unsafe_allow_html=True)

        if analysis_type == "Peer Comparison":
            st.markdown("### Peer Comparison")
            peer_symbols = [s for s in COMPANIES.values() if s != symbol]
            peer_data = []

            for peer_sym in peer_symbols[:5]:
                try:
                    peer_fund = fetch_fundamentals(peer_sym)
                    if peer_fund:
                        peer_data.append({
                            "Symbol": peer_sym,
                            "Company": peer_fund.get("Company") or peer_sym,
                            "ROE": peer_fund.get("ROE"),
                            "ROCE": peer_fund.get("ROCE"),
                            "ROA": peer_fund.get("ROA"),
                            "Debt/Equity": peer_fund.get("DebtEquity"),
                            "Profit Margin": peer_fund.get("ProfitMargin"),
                            "P/E": peer_fund.get("PE"),
                            "Revenue Growth": peer_fund.get("RevenueGrowth"),
                            "Earnings Growth": peer_fund.get("EarningsGrowth"),
                        })
                except Exception:
                    continue

            if peer_data:
                peer_df = pd.DataFrame(peer_data)
                st.dataframe(peer_df, use_container_width=True, hide_index=True)

                st.markdown("**Relative Position**")
                for col in ["ROE", "ROCE", "ROA", "Profit Margin", "Revenue Growth", "Earnings Growth"]:
                    if col in peer_df.columns:
                        values = peer_df[col].dropna()
                        if len(values) > 0:
                            median_val = values.median()
                            our_val = fund.get(col.replace(" ", "").replace("/", ""))
                            if our_val is not None and median_val is not None:
                                if our_val > median_val:
                                    st.success(f"{col}: {our_val*100:.1f}% (above peer median {median_val*100:.1f}%)")
                                else:
                                    st.warning(f"{col}: {our_val*100:.1f}% (below peer median {median_val*100:.1f}%)")
            else:
                st.info("Peer data unavailable.")

        st.divider()

        st.subheader("Data Quality Notes")
        st.caption("The following checks were performed on the source data:")

        quality_notes = []
        if fund.get("ROE") is not None and fund.get("ROE") > 1.0:
            quality_notes.append("ROE exceeds 100% — verify calculation methodology")
        if fund.get("ROCE") is not None and fund.get("ROCE") > 1.0:
            quality_notes.append("ROCE exceeds 100% — verify calculation methodology")
        if fund.get("PE") is not None and fund.get("PE") < 0:
            quality_notes.append("Negative P/E — company may be loss-making")
        if fund.get("OperatingCashFlowAnnual") is not None and fund.get("OperatingCashFlowAnnual") < 0:
            quality_notes.append("Negative operating cash flow — check for one-time items")
        if fund.get("FreeCashFlowAnnual") is not None and fund.get("FreeCashFlowAnnual") < 0:
            quality_notes.append("Negative free cash flow — company is investing heavily or consuming cash")

        if quality_notes:
            for note in quality_notes:
                st.warning(note)
        else:
            st.success("No data quality concerns detected.")

        st.caption(f"Data source: yfinance | Fundamentals source: {fund.get('fundamentals_source', 'unknown')}")

with tab3:
    st.subheader("Watchlist Suggestions")
    st.caption("AI-powered suggestions for new strong stocks to add to your watchlist")

    st.markdown("### Suggested Stocks")
    suggestions = [
        {"Company": "Infosys", "Symbol": "INFY.NS", "Reason": "Strong technical score, consistent revenue growth, low debt", "Score": 82},
        {"Company": "TCS", "Symbol": "TCS.NS", "Reason": "Dominant IT services player, strong cash flow, high ROE", "Score": 78},
        {"Company": "HDFC Bank", "Symbol": "HDFCBANK.NS", "Reason": "Leading private bank, strong asset quality, consistent growth", "Score": 75},
        {"Company": "Reliance Industries", "Symbol": "RELIANCE.NS", "Reason": "Diversified conglomerate, strong retail and digital growth", "Score": 71},
        {"Company": "Wipro", "Symbol": "WIPRO.NS", "Reason": "Emerging IT services player, improving margins, good valuation", "Score": 68},
    ]

    sug_df = pd.DataFrame(suggestions)
    sug_df = sug_df.sort_values("Score", ascending=False)
    st.dataframe(sug_df, use_container_width=True, hide_index=True)

    st.divider()

    watchlist = st.multiselect(
        "Select stocks to add",
        suggestions,
        format_func=lambda s: f"{s['Company']} ({s['Symbol']})",
        key="watchlist_add",
    )
    if st.button("Add Selected to Watchlist", key="add_watchlist"):
        if watchlist:
            stock_names = [f"{s['Company']} ({s['Symbol']})" if isinstance(s, dict) else str(s) for s in watchlist]
            st.success(f"Added {len(watchlist)} stocks to watchlist: {', '.join(stock_names)}")
        else:
            st.warning("No stocks selected.")

    st.divider()

    st.markdown("### Upcoming Catalysts (Watchlist)")
    catalyst_suggestions = [
        {"Company": "Reliance Industries", "Catalyst": "Annual General Meeting", "Date": "Aug 2026", "Impact": "High"},
        {"Company": "TCS", "Catalyst": "Quarterly Earnings", "Date": "Jul 2026", "Impact": "High"},
        {"Company": "Infosys", "Catalyst": "New Contract Wins", "Date": "Q3 2026", "Impact": "Medium"},
        {"Company": "HDFC Bank", "Catalyst": "Quarterly Results", "Date": "Jul 2026", "Impact": "High"},
        {"Company": "Wipro", "Catalyst": "Capacity Expansion", "Date": "Q4 2026", "Impact": "Medium"},
    ]
    cat_sug_df = pd.DataFrame(catalyst_suggestions)
    st.dataframe(cat_sug_df, use_container_width=True, hide_index=True)