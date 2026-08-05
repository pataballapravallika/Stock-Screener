import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from data.fetch_prices import fetch_prices
from data.fetch_fundamentals import fetch_fundamentals
from scoring.technical_score import compute_technical_indicators, score_technical, get_signal_explanation
from scoring.fundamental_score import score_fundamental, safe_float
from scoring.banking_score import score_banking
from scoring.combined_score import combined_score
from scoring.config import DEFAULT_CONFIG, score_category, signal_badge
from fundamentals.growth import calculate_growth_metrics
from fundamentals.banking import compute_banking_metrics
from fundamentals.altman import compute_altman_z
from fundamentals.piotroski import compute_piotroski_f_score
from patterns.patterns import swing_points, double_top, head_shoulders

st.set_page_config(page_title="Stock Analysis", layout="wide")

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

BENCHMARKS = {
    "NSE": "^NSEI",
    "US": "^GSPC",
}

company = st.sidebar.selectbox("Company", list(COMPANIES.keys()))
symbol = COMPANIES[company]

timeframe = st.sidebar.selectbox(
    "Timeframe",
    ["3M", "6M", "1Y", "3Y", "5Y", "10Y", "MAX"],
    index=2
)

PERIOD_MAP = {
    "3M": "3mo",
    "6M": "6mo",
    "1Y": "1y",
    "3Y": "3y",
    "5Y": "5y",
    "10Y": "10y",
    "MAX": "max",
}
period = PERIOD_MAP[timeframe]

with st.spinner("Loading historical data..."):
    df = fetch_prices(symbol, period=period)

if df.empty:
    st.error("No data returned for this ticker.")
    st.stop()

df = compute_technical_indicators(df)
latest = df.iloc[-1]
tech_result = score_technical(latest)
signal_explanation = get_signal_explanation(tech_result["conditions"], tech_result["signal"])

try:
    fund = fetch_fundamentals(symbol) or {}
except Exception:
    fund = {}

sector = fund.get("Sector") or ""
is_bank = any(b.lower() in sector.lower() for b in BANK_SECTORS)

fund_for_scoring = {
    "EPS_Growth": fund.get("EarningsGrowth"),
    "Revenue_Growth": fund.get("RevenueGrowth"),
    "PAT_Growth": None,
    "ROE": fund.get("ROE"),
    "ROCE": fund.get("ROCE"),
    "ROA": fund.get("ROA"),
    "Debt_Equity": fund.get("DebtEquity"),
}

if is_bank:
    bank_data = {
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
    bank_result = score_banking(bank_data)
    fund_score_result = {"percentage": bank_result["percentage"], "signal": bank_result["signal"]}
else:
    fund_score_result = score_fundamental(fund_for_scoring)

combined = combined_score(
    technical_result=tech_result,
    fundamental_result=fund_score_result,
    is_bank=is_bank,
)

tech_cat = score_category(tech_result["percentage"])
fund_cat = score_category(fund_score_result["percentage"])
combined_cat = score_category(combined["combined_percentage"])

price_strength = (
    latest["Close"] / latest["52W_High"] * 100
    if pd.notna(latest["52W_High"]) and latest["52W_High"] != 0
    else None
)
price_strength_pct = f"{price_strength:.0f}%" if price_strength is not None else "N/A"

eps_growth = fund.get("EarningsGrowth")
eps_growth_str = f"{eps_growth*100:.1f}%" if eps_growth is not None else "N/A"

volume_ratio = (
    latest["Volume"] / latest["Volume_MA20"]
    if pd.notna(latest.get("Volume_MA20")) and latest.get("Volume_MA20", 0) > 0
    else None
)
volume_demand = (
    "A+" if volume_ratio and volume_ratio > 2 else
    "A" if volume_ratio and volume_ratio > 1.5 else
    "B+" if volume_ratio and volume_ratio > 1.2 else
    "B" if volume_ratio and volume_ratio > 1.0 else
    "C"
    if volume_ratio is not None
    else "N/A"
)

st.title(f"{company} Analysis")
st.caption(f"{symbol} | {sector or 'N/A'} | Combined signal: {signal_badge(combined['combined_signal'])}")

# ============================================================
# TOP RATING CARDS
# ============================================================

c1, c2, c3, c4, c5, c6, c7 = st.columns(7)

with c1:
    st.metric("Technical Score", f"{tech_result['percentage']:.0f}/100", tech_cat)
with c2:
    st.metric("Fundamental Score", f"{fund_score_result['percentage']:.0f}/100", fund_cat)
with c3:
    st.metric("Price Strength", price_strength_pct, score_category(price_strength) if price_strength is not None else "N/A")
with c4:
    st.metric("EPS Growth", eps_growth_str, "N/A" if eps_growth is None else ("Positive" if eps_growth > 0 else "Negative"))
with c5:
    st.metric("Volume Demand", volume_demand, f"{volume_ratio:.1f}x" if volume_ratio is not None else "N/A")
with c6:
    st.metric("Combined Score", f"{combined['combined_percentage']:.0f}/100", combined_cat)
with c7:
    st.metric("Signal", combined["combined_signal"], signal_badge(combined["combined_signal"]))

st.divider()

# ============================================================
# BUY / HOLD / SELL DECISION PANEL
# ============================================================

st.subheader("Current Signal")
signal_col, explanation_col = st.columns([1, 3])

with signal_col:
    signal_color = (
        "#d4edda" if combined["combined_signal"] == "BUY" else
        "#f8d7da" if combined["combined_signal"] == "SELL" else
        "#fff3cd"
    )
    signal_text_color = (
        "#155724" if combined["combined_signal"] == "BUY" else
        "#721c24" if combined["combined_signal"] == "SELL" else
        "#856404"
    )
    st.markdown(
        f"<div style='background-color:{signal_color}; color:{signal_text_color}; padding:20px; border-radius:10px; text-align:center;'>"
        f"<h1 style='margin:0;'>{combined['combined_signal']}</h1>"
        f"<p style='margin:5px 0 0 0;'>Combined: {combined['combined_percentage']:.0f}/100</p>"
        f"</div>",
        unsafe_allow_html=True
    )

with explanation_col:
    st.write("**Why?**")
    bullet_points = []
    conditions = tech_result["conditions"]
    bullet_points.append(f"✓ Technical score = {tech_result['percentage']:.0f}% ({tech_result['signal']})")
    bullet_points.append(f"✓ Fundamental score = {fund_score_result['percentage']:.0f}% ({fund_score_result.get('signal', 'N/A')})")
    for cond, met in conditions.items():
        icon = "✓" if met else "✗"
        bullet_points.append(f"{icon} {cond.replace('_', ' ').title()}")
    if fund_score_result.get("unavailable"):
        bullet_points.append(f"⚠ Unavailable fundamentals: {', '.join(fund_score_result['unavailable'])}")
    st.write("\n".join(bullet_points))

st.divider()

# ============================================================
# MAIN PRICE CHART
# ============================================================

st.subheader("Price Chart")

# Filter dataframe based on timeframe selection
if timeframe != "MAX":
    cutoff_date = latest["Date"] - pd.Timedelta(days={
        "3M": 90, "6M": 180, "1Y": 365, "3Y": 1095, "5Y": 1825, "10Y": 3650
    }[timeframe])
    chart_df = df[df["Date"] >= cutoff_date].copy()
else:
    chart_df = df.copy()

# Detect patterns
chart_df = swing_points(chart_df, distance=10)
chart_df = double_top(chart_df, tolerance=0.03)
chart_df = head_shoulders(chart_df, tolerance=0.05)

# Buy/Sell markers
chart_df["Buy_Signal"] = np.nan
chart_df["Sell_Signal"] = np.nan

# Simple signal generation for markers
tech_signals = []
for i in range(len(chart_df)):
    row = chart_df.iloc[i]
    res = score_technical(row)
    if res["signal"] == "BUY":
        tech_signals.append(1)
    elif res["signal"] == "SELL":
        tech_signals.append(-1)
    else:
        tech_signals.append(0)

chart_df["Tech_Signal_Raw"] = tech_signals

for i in range(1, len(chart_df)):
    if chart_df.iloc[i]["Tech_Signal_Raw"] == 1 and chart_df.iloc[i-1]["Tech_Signal_Raw"] != 1:
        chart_df.iloc[i, chart_df.columns.get_loc("Buy_Signal")] = chart_df.iloc[i]["Low"] * 0.995
    elif chart_df.iloc[i]["Tech_Signal_Raw"] == -1 and chart_df.iloc[i-1]["Tech_Signal_Raw"] != -1:
        chart_df.iloc[i, chart_df.columns.get_loc("Sell_Signal")] = chart_df.iloc[i]["High"] * 1.005

price_fig = make_subplots(
    rows=3, cols=1,
    shared_xaxes=True,
    vertical_spacing=0.03,
    row_heights=[0.6, 0.2, 0.2],
    subplot_titles=("Price", "Volume", "RSI")
)

# Candlesticks
price_fig.add_trace(
    go.Candlestick(
        x=chart_df["Date"],
        open=chart_df["Open"],
        high=chart_df["High"],
        low=chart_df["Low"],
        close=chart_df["Close"],
        name="OHLC",
        increasing_line_color="green",
        decreasing_line_color="red",
    ),
    row=1, col=1
)

# MAs
for ma, color in [("MA20", "gray"), ("MA50", "blue"), ("MA200", "orange")]:
    if ma in chart_df.columns:
        price_fig.add_trace(
            go.Scatter(x=chart_df["Date"], y=chart_df[ma], mode="lines", name=ma, line=dict(color=color, width=1)),
            row=1, col=1
        )

# 52-week high
if "52W_High" in chart_df.columns:
    price_fig.add_trace(
        go.Scatter(x=chart_df["Date"], y=chart_df["52W_High"], mode="lines", name="52W High", line=dict(color="purple", width=1, dash="dot")),
        row=1, col=1
    )

# Buy/Sell markers
buy_signals = chart_df[chart_df["Buy_Signal"].notna()]
sell_signals = chart_df[chart_df["Sell_Signal"].notna()]

price_fig.add_trace(
    go.Scatter(x=buy_signals["Date"], y=buy_signals["Buy_Signal"], mode="markers", name="BUY", marker=dict(symbol="triangle-up", color="green", size=12)),
    row=1, col=1
)
price_fig.add_trace(
    go.Scatter(x=sell_signals["Date"], y=sell_signals["Sell_Signal"], mode="markers", name="SELL", marker=dict(symbol="triangle-down", color="red", size=12)),
    row=1, col=1
)

# Swing points
swing_highs = chart_df[chart_df["SwingHigh"] == True]
swing_lows = chart_df[chart_df["SwingLow"] == True]
price_fig.add_trace(
    go.Scatter(x=swing_highs["Date"], y=swing_highs["High"], mode="markers", name="Swing High", marker=dict(symbol="circle", color="orange", size=6)),
    row=1, col=1
)
price_fig.add_trace(
    go.Scatter(x=swing_lows["Date"], y=swing_lows["Low"], mode="markers", name="Swing Low", marker=dict(symbol="circle", color="cyan", size=6)),
    row=1, col=1
)

# Volume
colors_volume = ["green" if chart_df["Close"].iloc[i] >= chart_df["Open"].iloc[i] else "red" for i in range(len(chart_df))]
price_fig.add_trace(
    go.Bar(x=chart_df["Date"], y=chart_df["Volume"], name="Volume", marker_color=colors_volume, opacity=0.7),
    row=2, col=1
)
if "Volume_MA20" in chart_df.columns:
    price_fig.add_trace(
        go.Scatter(x=chart_df["Date"], y=chart_df["Volume_MA20"], mode="lines", name="Vol MA20", line=dict(color="blue", width=1)),
        row=2, col=1
    )

# RSI
if "RSI" in chart_df.columns:
    price_fig.add_trace(
        go.Scatter(x=chart_df["Date"], y=chart_df["RSI"], mode="lines", name="RSI", line=dict(color="purple")),
        row=3, col=1
    )
    price_fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
    price_fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)
    price_fig.add_hrect(y0=70, y1=100, line_width=0, fillcolor="red", opacity=0.1, row=3, col=1)
    price_fig.add_hrect(y0=0, y1=30, line_width=0, fillcolor="green", opacity=0.1, row=3, col=1)

price_fig.update_layout(
    height=900,
    xaxis_rangeslider_visible=False,
    hovermode="x unified",
    showlegend=True,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)

st.plotly_chart(price_fig, use_container_width=True)

# ============================================================
# RELATIVE STRENGTH
# ============================================================

st.subheader("Relative Strength")

is_indian = symbol.endswith(".NS") or symbol.endswith(".BO")
benchmark_symbol = BENCHMARKS["NSE"] if is_indian else BENCHMARKS["US"]

try:
    bench_df = fetch_prices(benchmark_symbol, period=period)
    if not bench_df.empty:
        bench_df = bench_df.set_index("Date")
        stock_prices = chart_df.set_index("Date")["Close"]
        bench_prices = bench_df["Close"]

        common_dates = stock_prices.index.intersection(bench_prices.index)
        if len(common_dates) > 0:
            stock_norm = stock_prices.loc[common_dates] / stock_prices.loc[common_dates].iloc[0] * 100
            bench_norm = bench_prices.loc[common_dates] / bench_prices.loc[common_dates].iloc[0] * 100

            rs_fig = go.Figure()
            rs_fig.add_trace(go.Scatter(x=stock_norm.index, y=stock_norm, mode="lines", name=symbol, line=dict(color="blue")))
            rs_fig.add_trace(go.Scatter(x=bench_norm.index, y=bench_norm, mode="lines", name=benchmark_symbol, line=dict(color="gray", dash="dash")))
            rs_fig.update_layout(
                title=f"{symbol} vs {benchmark_symbol} (Normalized to 100)",
                height=400,
                xaxis_title="Date",
                yaxis_title="Normalized Price",
                hovermode="x unified"
            )
            st.plotly_chart(rs_fig, use_container_width=True)

            stock_last = float(stock_norm.iloc[-1])
            bench_last = float(bench_norm.iloc[-1])

            if stock_last > bench_last:
                st.success(f"**{symbol}** is outperforming {benchmark_symbol} over this period.")
            else:
                st.warning(f"**{symbol}** is underperforming {benchmark_symbol} over this period.")
        else:
            st.info("No overlapping dates for relative strength comparison.")
    else:
        st.info("Benchmark data unavailable.")
except Exception as e:
    st.info(f"Relative strength unavailable: {e}")

# ============================================================
# VOLUME PANEL
# ============================================================

st.subheader("Volume Analysis")

high_volume_days = chart_df[chart_df["Volume"] > 1.5 * chart_df["Volume_MA20"].fillna(0)]

volume_fig = go.Figure()
volume_fig.add_trace(
    go.Bar(
        x=chart_df["Date"],
        y=chart_df["Volume"],
        name="Volume",
        marker_color=["rgba(0,200,0,0.6)" if c >= o else "rgba(200,0,0,0.6)" for c, o in zip(chart_df["Close"], chart_df["Open"])]
    )
)
if "Volume_MA20" in chart_df.columns:
    volume_fig.add_trace(
        go.Scatter(x=chart_df["Date"], y=chart_df["Volume_MA20"], mode="lines", name="20-Day Average", line=dict(color="blue", width=2))
    )

if not high_volume_days.empty:
    volume_fig.add_trace(
        go.Scatter(
            x=high_volume_days["Date"],
            y=high_volume_days["Volume"],
            mode="markers",
            name="High Volume (>1.5x avg)",
            marker=dict(symbol="circle", color="orange", size=8, line=dict(color="black", width=1))
        )
    )

volume_fig.update_layout(
    height=400,
    xaxis_title="Date",
    yaxis_title="Volume",
    hovermode="x unified"
)
st.plotly_chart(volume_fig, use_container_width=True)

vol_col1, vol_col2, vol_col3 = st.columns(3)
with vol_col1:
    st.metric("Volume Ratio", f"{volume_ratio:.2f}x" if volume_ratio is not None else "N/A")
with vol_col2:
    st.metric("High Volume Days", len(high_volume_days))
with vol_col3:
    avg_vol = chart_df["Volume"].mean()
    st.metric("Average Volume", f"{avg_vol:,.0f}")

# ============================================================
# TECHNICAL INDICATOR TABS
# ============================================================

st.divider()
st.subheader("Technical Indicators")

indicator_tab = st.tabs(["RSI", "MACD", "Stochastic", "ATR / ADR", "Bollinger Bands", "SuperTrend"])

with indicator_tab[0]:
    rsi_fig = go.Figure()
    rsi_fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["RSI"], mode="lines", name="RSI", line=dict(color="purple")))
    rsi_fig.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="Overbought (70)")
    rsi_fig.add_hline(y=30, line_dash="dash", line_color="green", annotation_text="Oversold (30)")
    rsi_fig.add_hrect(y0=70, y1=100, line_width=0, fillcolor="red", opacity=0.1)
    rsi_fig.add_hrect(y0=0, y1=30, line_width=0, fillcolor="green", opacity=0.1)
    rsi_fig.update_layout(height=400, yaxis_range=[0, 100], xaxis_title="Date", yaxis_title="RSI")
    st.plotly_chart(rsi_fig, use_container_width=True)

with indicator_tab[1]:
    macd_fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
    macd_fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["MACD"], mode="lines", name="MACD", line=dict(color="blue")), row=1, col=1)
    macd_fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["MACD_Signal"], mode="lines", name="Signal", line=dict(color="orange")), row=1, col=1)
    macd_fig.add_trace(go.Bar(x=chart_df["Date"], y=chart_df["MACD_Hist"], name="Histogram", marker_color="gray"), row=2, col=1)
    macd_fig.add_hline(y=0, line_dash="dash", line_color="black", row=2, col=1)
    macd_fig.update_layout(height=500, xaxis_title="Date", yaxis_title="MACD", showlegend=True)
    st.plotly_chart(macd_fig, use_container_width=True)

with indicator_tab[2]:
    stoch_fig = go.Figure()
    stoch_fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["Stochastic_K"], mode="lines", name="%K", line=dict(color="blue")))
    stoch_fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["Stochastic_D"], mode="lines", name="%D", line=dict(color="orange")))
    stoch_fig.add_hline(y=80, line_dash="dash", line_color="red")
    stoch_fig.add_hline(y=20, line_dash="dash", line_color="green")
    stoch_fig.update_layout(height=400, yaxis_range=[0, 100], xaxis_title="Date", yaxis_title="Stochastic")
    st.plotly_chart(stoch_fig, use_container_width=True)

with indicator_tab[3]:
    atr_fig = go.Figure()
    atr_fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["ATR"], mode="lines", name="ATR (14)", line=dict(color="red")))
    atr_fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["ADR"], mode="lines", name="ADR (20)", line=dict(color="blue")))
    atr_fig.update_layout(height=400, xaxis_title="Date", yaxis_title="Volatility (%)", hovermode="x unified")
    st.plotly_chart(atr_fig, use_container_width=True)

with indicator_tab[4]:
    bb_fig = go.Figure()
    bb_fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["Close"], mode="lines", name="Close", line=dict(color="black")))
    bb_fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["BB_Upper"], mode="lines", name="Upper Band", line=dict(color="gray", dash="dash")))
    bb_fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["BB_Middle"], mode="lines", name="Middle Band", line=dict(color="blue")))
    bb_fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["BB_Lower"], mode="lines", name="Lower Band", line=dict(color="gray", dash="dash")))
    bb_fig.update_layout(height=400, xaxis_title="Date", yaxis_title="Price", hovermode="x unified")
    st.plotly_chart(bb_fig, use_container_width=True)

with indicator_tab[5]:
    st_fig = go.Figure()
    st_fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["Close"], mode="lines", name="Close", line=dict(color="black")))
    st_fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["SuperTrend_Line"], mode="lines", name="SuperTrend", line=dict(color="green" if chart_df["SuperTrend"].iloc[-1] == 1 else "red")))
    st_fig.update_layout(height=400, xaxis_title="Date", yaxis_title="Price", hovermode="x unified")
    st.plotly_chart(st_fig, use_container_width=True)

# ============================================================
# PATTERN VISUALIZATION
# ============================================================

st.divider()
st.subheader("Pattern Detection")

patterns_found = []
if "DoubleTop" in chart_df.columns and chart_df["DoubleTop"].any():
    patterns_found.append({"Pattern": "Double Top", "Status": "Detected", "Count": chart_df["DoubleTop"].sum()})
if "HeadShoulders" in chart_df.columns and chart_df["HeadShoulders"].any():
    patterns_found.append({"Pattern": "Head & Shoulders", "Status": "Detected", "Count": chart_df["HeadShoulders"].sum()})
if chart_df["Breakout"].any():
    patterns_found.append({"Pattern": "Breakout", "Status": "Detected", "Count": chart_df["Breakout"].sum()})

if patterns_found:
    pattern_df = pd.DataFrame(patterns_found)
    st.dataframe(pattern_df, use_container_width=True, hide_index=True)
else:
    st.info("No significant patterns detected in the selected timeframe.")

# ============================================================
# QUARTERLY FUNDAMENTALS
# ============================================================

st.divider()
st.subheader("Quarterly Fundamentals")

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

quarterly_growth = {}
if income_stmt is not None and not income_stmt.empty:
    quarterly_growth = calculate_growth_metrics(income_stmt, quarterly=True)

if quarterly_growth:
    q_display = []
    for k in ["Revenue", "EPS", "PAT", "Operating_Profit", "OPM", "NPM"]:
        if k in quarterly_growth:
            val = quarterly_growth[k]
            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                if "Growth" in k:
                    q_display.append({"Metric": k, "Value": f"{val*100:.2f}%"})
                else:
                    q_display.append({"Metric": k, "Value": f"{val:.2f}"})
    if q_display:
        st.dataframe(pd.DataFrame(q_display), use_container_width=True, hide_index=True)
    else:
        st.info("Quarterly data unavailable.")
else:
    st.info("Quarterly fundamentals unavailable from current data provider.")

# Quarterly growth charts
if quarterly_growth:
    st.subheader("Quarterly Growth Charts")
    growth_metrics = {k: v for k, v in quarterly_growth.items() if "Growth" in k and v is not None}
    if growth_metrics:
        growth_df = pd.DataFrame([
            {"Metric": k.replace("_Growth", "").replace("_", " ").title(), "Growth": v * 100}
            for k, v in growth_metrics.items()
        ])
        if not growth_df.empty:
            bar_fig = px.bar(growth_df, x="Metric", y="Growth", color="Growth", color_continuous_scale="RdYlGn", title="Quarterly Growth (%)")
            bar_fig.update_layout(height=400)
            st.plotly_chart(bar_fig, use_container_width=True)

# ============================================================
# 3-YEAR FUNDAMENTAL TRENDS
# ============================================================

st.divider()
st.subheader("3-Year Fundamental Performance")

annual_data = {}
if income_stmt is not None and not income_stmt.empty:
    annual_data = calculate_growth_metrics(income_stmt, quarterly=False)

if annual_data:
    trend_rows = []
    for key in sorted(annual_data.keys()):
        if "Year_" in key:
            year = key.replace("Year_", "")
            row = {"Year": year}
            for metric in ["Revenue", "PAT", "EPS", "ROE", "ROCE", "ROA", "Debt_Equity"]:
                search_key = f"Year_{year}_{metric}"
                if search_key in annual_data:
                    row[metric] = annual_data[search_key]
                else:
                    row[metric] = None
            trend_rows.append(row)

    if trend_rows:
        trend_df = pd.DataFrame(trend_rows)
        st.dataframe(trend_df, use_container_width=True, hide_index=True)

        revenues = [r["Revenue"] for r in trend_rows if r.get("Revenue") is not None]
        pats = [r["PAT"] for r in trend_rows if r.get("PAT") is not None]

        if len(revenues) >= 2:
            rev_cagr = (revenues[0] / revenues[-1]) ** (1 / (len(revenues) - 1)) - 1
            st.metric("3Y Revenue CAGR", f"{rev_cagr*100:.1f}%")
        if len(pats) >= 2:
            pat_cagr = (pats[0] / pats[-1]) ** (1 / (len(pats) - 1)) - 1
            st.metric("3Y PAT CAGR", f"{pat_cagr*100:.1f}%")
else:
    st.info("3-year fundamental trend data unavailable.")

# ============================================================
# SHAREHOLDING / BANKING
# ============================================================

st.divider()

if is_bank:
    st.subheader("Banking Fundamentals")
    try:
        bank_display = compute_banking_metrics(bank_data, {})
        bank_rows = []
        for k, v in bank_display.items():
            if k == "missing":
                continue
            display_v = f"{v:.2f}%" if isinstance(v, float) else str(v)
            bank_rows.append({"Metric": k, "Value": display_v})
        if bank_rows:
            st.dataframe(pd.DataFrame(bank_rows), use_container_width=True, hide_index=True)
    except Exception as e:
        st.info(f"Banking data unavailable: {e}")
else:
    st.subheader("Shareholding Pattern")
    try:
        ticker = yf.Ticker(symbol)
        holders = ticker.major_holders
        if holders is not None and not holders.empty:
            st.dataframe(holders, use_container_width=True)
        else:
            st.info("Historical Promoter/FII/DII data requires an additional data source.")
    except Exception:
        st.info("Historical Promoter/FII/DII data requires an additional data source.")

# ============================================================
# FUNDAMENTAL STRENGTH MATRIX
# ============================================================

st.divider()
st.subheader("Fundamental Strength Matrix")

matrix_data = []

def add_matrix_row(name, current, previous=None, growth=None, score_val=None, status=""):
    matrix_data.append({
        "Metric": name,
        "Current": f"{current:.2f}" if current is not None else "N/A",
        "Previous": f"{previous:.2f}" if previous is not None else "N/A",
        "Growth": f"{growth*100:.2f}%" if growth is not None else "N/A",
        "Score": score_val if score_val is not None else "N/A",
        "Status": status,
    })

def safe_score(fund, key, threshold, comparator=">"):
    val = safe_float(fund.get(key))
    if val is None:
        return "N/A"
    if comparator == ">" and val > threshold:
        return "Pass"
    elif comparator == "<" and val < threshold:
        return "Pass"
    return "Fail"

add_matrix_row("EPS Growth", fund.get("EarningsGrowth"), score_val=safe_score(fund, "EarningsGrowth", 0.10, ">"))
add_matrix_row("Revenue Growth", fund.get("RevenueGrowth"), score_val=safe_score(fund, "RevenueGrowth", 0.10, ">"))
add_matrix_row("PAT Growth", None, score_val="N/A")
add_matrix_row("ROE", fund.get("ROE"), score_val=safe_score(fund, "ROE", 0.15, ">"))
add_matrix_row("ROCE", fund.get("ROCE"), score_val=safe_score(fund, "ROCE", 0.15, ">"))
add_matrix_row("ROA", fund.get("ROA"), score_val=safe_score(fund, "ROA", 0.05, ">"))
add_matrix_row("Debt/Equity", fund.get("DebtEquity"), score_val=safe_score(fund, "DebtEquity", 100, "<"))
add_matrix_row("Operating Cash Flow", fund.get("OperatingCashFlow"), score_val="Pass" if fund.get("OperatingCashFlow") is not None else "N/A")
add_matrix_row("Piotroski F-Score", None, score_val="N/A")
add_matrix_row("Altman Z-Score", None, score_val="N/A")

if matrix_data:
    matrix_df = pd.DataFrame(matrix_data)

    def color_status(val):
        if val == "Pass":
            return "background-color: #d4edda; color: #155724;"
        elif val == "Fail":
            return "background-color: #f8d7da; color: #721c24;"
        else:
            return ""

    styled_matrix = matrix_df.style.map(color_status, subset=["Score", "Status"])
    st.dataframe(styled_matrix, use_container_width=True, hide_index=True)

# ============================================================
# TECHNICAL SUMMARY
# ============================================================

st.divider()
st.subheader("Technical Summary")

summary_data = {
    "Indicator": ["Close", "MA20", "MA50", "MA200", "RSI", "MACD", "MACD Signal", "VWAP",
                  "Stochastic %K", "Stochastic %D", "52-Week High", "Distance From 52W High", "Breakout"],
    "Value": [
        latest["Close"], latest["MA20"], latest["MA50"], latest["MA200"],
        latest["RSI"], latest["MACD"], latest["MACD_Signal"], latest.get("VWAP", "N/A"),
        latest.get("Stochastic_K", "N/A"), latest.get("Stochastic_D", "N/A"),
        latest["52W_High"], latest["Distance_52W_High"], latest["Breakout"]
    ]
}
st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)

st.divider()
st.subheader("Signal Conditions")
conditions = tech_result["conditions"]
signal_rows = []
for cond, met in conditions.items():
    signal_rows.append({"Condition": cond.replace("_", " ").title(), "Met": "Yes" if met else "No"})
st.dataframe(pd.DataFrame(signal_rows), use_container_width=True, hide_index=True)

st.divider()
st.subheader("Recent OHLCV Data")
recent_data = df[["Date", "Open", "High", "Low", "Close", "Volume"]].tail(20).sort_values("Date", ascending=False)
st.dataframe(recent_data, use_container_width=True, hide_index=True)

csv = df.to_csv(index=False).encode("utf-8")
st.download_button(
    "Download Historical CSV",
    csv,
    f"{symbol}_historical_data.csv",
    "text/csv"
)
