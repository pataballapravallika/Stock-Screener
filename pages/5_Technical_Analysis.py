import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from data.fetch_prices import fetch_prices
from data.fetch_fundamentals import fetch_fundamentals
from scoring.technical_score import compute_technical_indicators, score_technical
from patterns.patterns import swing_points, double_top, head_shoulders
from fundamentals.ratios import safe_float

st.set_page_config(page_title="Technical Analysis", layout="wide")

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

BENCHMARK_SYMBOLS = {
    "NIFTY 500": "^CRSLDX",
    "NIFTY 50": "^NSEI",
}

st.title("Technical Analysis")
st.caption("RS Rating, VCP stage, EMA alignment, Volume ratio, Breakout status, Trend stage, Pattern Recognition")

company = st.selectbox("Company", list(COMPANIES.keys()))
symbol = COMPANIES[company]
benchmark = st.selectbox("Benchmark", list(BENCHMARK_SYMBOLS.keys()))
bench_symbol = BENCHMARK_SYMBOLS[benchmark]

@st.cache_data(ttl=1800)
def load_technical_data(symbol, bench_symbol):
    df = fetch_prices(symbol, period="1y")
    bench_df = fetch_prices(bench_symbol, period="1y")
    return df, bench_df

df, bench_df = load_technical_data(symbol, bench_symbol)

if df.empty:
    st.error("No data available for this ticker.")
    st.stop()

df = compute_technical_indicators(df)
latest = df.iloc[-1]
tech_result = score_technical(latest)

from indicators.vwap_engine import compute_session_vwap

vwap_res = compute_session_vwap(symbol)
session_vwap_val = vwap_res.get("session_vwap")
session_vwap_str = f"₹{session_vwap_val:,.2f}" if session_vwap_val else "N/A"
vwap_diff_str = f"{vwap_res.get('vwap_diff', 0):+.2f} ({vwap_res.get('vwap_diff_pct', 0):+.2f}%)" if session_vwap_val else None

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("RS Rating", f"{tech_result['percentage']:.0f}/100")
c1.metric("Signal", tech_result["signal"])

c2.metric(
    "Intraday Session VWAP",
    session_vwap_str,
    delta=vwap_diff_str,
    help=f"Exact 5m Intraday Session VWAP ({vwap_res.get('timeframe', '5m Session')} for {vwap_res.get('session_date', 'Today')})"
)

ema_cols = ["EMA9", "EMA21", "EMA50", "EMA100", "EMA150", "EMA200"]
ema_vals = [latest.get(c) for c in ema_cols]
ema_alignment = all(ema_vals[i] > ema_vals[i+1] for i in range(len(ema_vals)-1)) if all(pd.notna(v) for v in ema_vals) else None
c3.metric("EMA Alignment", "Bullish" if ema_alignment else "Bearish/Mixed" if ema_alignment is False else "N/A")

vol_ratio = latest["Volume"] / latest["Volume_MA20"] if pd.notna(latest.get("Volume_MA20")) and latest.get("Volume_MA20", 0) > 0 else None
c3.metric("Volume Ratio", f"{vol_ratio:.2f}x" if vol_ratio else "N/A")

breakout_status = latest.get("Breakout", False)
c4.metric("Breakout", "Confirmed" if breakout_status else "No Breakout")

dist_52w = latest.get("Distance_52W_High")
if pd.notna(dist_52w):
    if dist_52w >= -5:
        trend_stage = "Near 52W High"
    elif dist_52w >= -20:
        trend_stage = "Mid-Range"
    else:
        trend_stage = "Low Range"
else:
    trend_stage = "N/A"
c5.metric("Trend Stage", trend_stage)

st.divider()

st.markdown("### VCP (Volatility Contraction Pattern) Stage")
atr = latest.get("ATR")
bb_upper = latest.get("BB_Upper")
bb_lower = latest.get("BB_Lower")
adx = latest.get("ADX")

vcp_indicators = []
if pd.notna(atr):
    atr_20 = df["ATR"].rolling(20).mean().iloc[-1]
    atr_contraction = atr < atr_20 * 0.8
    vcp_indicators.append(("ATR Contraction", atr_contraction))

if pd.notna(bb_upper) and pd.notna(bb_lower) and pd.notna(latest.get("Close")):
    bb_width = (bb_upper - bb_lower) / latest["Close"] * 100
    bb_squeeze = bb_width < 5
    vcp_indicators.append(("Bollinger Squeeze", bb_squeeze))

if pd.notna(adx):
    adx_trend = adx > 25
    vcp_indicators.append(("ADX > 25 (Trend)", adx_trend))

for name, val in vcp_indicators:
    status = "Active" if val else "Inactive"
    color = "green" if val else "gray"
    st.markdown(f"- **{name}**: {status}")

vcp_stage = "VCP Building" if sum(1 for _, v in vcp_indicators if v) >= 2 else "Base Building" if sum(1 for _, v in vcp_indicators if v) >= 1 else "No VCP"
st.metric("VCP Stage", vcp_stage)

st.divider()

st.markdown("### RS Rating vs Benchmark & Sector")

if not bench_df.empty:
    bench_latest = bench_df.iloc[-1]["Close"]
    bench_start = bench_df.iloc[0]["Close"]
    bench_return = (bench_latest - bench_start) / bench_start * 100

    stock_latest = latest["Close"]
    stock_start = df.iloc[0]["Close"]
    stock_return = (stock_latest - stock_start) / stock_start * 100

    rs_vs_bench = stock_return - bench_return

    c1, c2, c3 = st.columns(3)
    c1.metric(f"RS vs {benchmark}", f"{rs_vs_bench:+.2f}%")
    c2.metric("Stock Return (1Y)", f"{stock_return:.2f}%")
    c3.metric(f"{benchmark} Return (1Y)", f"{bench_return:.2f}%")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["Date"], y=df["Close"]/df["Close"].iloc[0]*100, name=company))
    fig.add_trace(go.Scatter(x=bench_df["Date"], y=bench_df["Close"]/bench_df["Close"].iloc[0]*100, name=benchmark))
    fig.update_layout(height=350, yaxis_title="Normalized Return (Base=100)", xaxis_title="Date")
    st.plotly_chart(fig, use_container_width=True)

st.divider()

st.markdown("### Pattern Recognition")

df_with_swings = swing_points(df.copy())
df_with_dt = double_top(df_with_swings.copy())
df_with_hs = head_shoulders(df_with_dt.copy())

latest_idx = df_with_hs.index[-1]

patterns_found = []
if df_with_hs.loc[latest_idx, "DoubleTop"]:
    patterns_found.append("Double Top")
if df_with_hs.loc[latest_idx, "HeadShoulders"]:
    patterns_found.append("Head & Shoulders")

swing_highs = df_with_hs[df_with_hs["SwingHigh"]]
swing_lows = df_with_hs[df_with_hs["SwingLow"]]

if len(swing_highs) >= 2:
    last_high = swing_highs.iloc[-1]["High"]
    prev_high = swing_highs.iloc[-2]["High"]
    if abs(last_high - prev_high) / prev_high < 0.03:
        patterns_found.append("Double Top (Swing)")

if len(swing_lows) >= 2:
    last_low = swing_lows.iloc[-1]["Low"]
    prev_low = swing_lows.iloc[-2]["Low"]
    if abs(last_low - prev_low) / prev_low < 0.03:
        patterns_found.append("Double Bottom (Swing)")

if latest.get("Close") and latest.get("BB_Lower") and latest.get("BB_Upper"):
    close = latest["Close"]
    bb_l = latest["BB_Lower"]
    bb_u = latest["BB_Upper"]
    bb_mid = latest.get("BB_Middle", (bb_u + bb_l) / 2)
    if close <= bb_l * 1.01:
        patterns_found.append("Near Lower Bollinger Band")
    elif close >= bb_u * 0.99:
        patterns_found.append("Near Upper Bollinger Band")

if pd.notna(latest.get("Stochastic_K")) and latest.get("Stochastic_K") < 20:
    patterns_found.append("Oversold (Stochastic)")
elif pd.notna(latest.get("Stochastic_K")) and latest.get("Stochastic_K") > 80:
    patterns_found.append("Overbought (Stochastic)")

if patterns_found:
    for p in patterns_found:
        st.markdown(f"- 📊 **{p}**")
else:
    st.caption("No significant patterns detected at current price level.")

st.divider()

st.markdown("### Breakout Status Detail")
bs = latest.get("Breakout", False)
near_52w = pd.notna(dist_52w) and dist_52w > -5
if bs:
    st.success("Confirmed Breakout — Price above recent highs with volume support.")
elif near_52w:
    st.warning("Near Breakout — Price approaching 52-week high. Watch for confirmation.")
elif pd.notna(dist_52w) and dist_52w < -20:
    st.info("Base Building — Price is well below 52-week high, consolidating for next move.")
else:
    st.info("Monitoring — No clear breakout or base-building pattern yet.")

st.divider()

st.markdown("### Technical Indicators Summary")
indicator_df = pd.DataFrame({
    "Indicator": ["RSI", "MACD", "MACD Signal", "RSI(14)", "ADX", "ATR", "Stochastic %K", "Stochastic %D", "SuperTrend", "Volume Ratio", "Distance 52W High"],
    "Value": [
        f"{latest.get('RSI', 0):.2f}" if pd.notna(latest.get('RSI')) else "N/A",
        f"{latest.get('MACD', 0):.4f}" if pd.notna(latest.get('MACD')) else "N/A",
        f"{latest.get('MACD_Signal', 0):.4f}" if pd.notna(latest.get('MACD_Signal')) else "N/A",
        f"{latest.get('RSI', 0):.2f}" if pd.notna(latest.get('RSI')) else "N/A",
        f"{latest.get('ADX', 0):.2f}" if pd.notna(latest.get('ADX')) else "N/A",
        f"{latest.get('ATR', 0):.2f}" if pd.notna(latest.get('ATR')) else "N/A",
        f"{latest.get('Stochastic_K', 0):.2f}" if pd.notna(latest.get('Stochastic_K')) else "N/A",
        f"{latest.get('Stochastic_D', 0):.2f}" if pd.notna(latest.get('Stochastic_D')) else "N/A",
        f"{latest.get('SuperTrend', 0):.0f}" if pd.notna(latest.get('SuperTrend')) else "N/A",
        f"{vol_ratio:.2f}x" if vol_ratio else "N/A",
        f"{dist_52w:.2f}%" if pd.notna(dist_52w) else "N/A",
    ]
})
st.dataframe(indicator_df, use_container_width=True, hide_index=True)

st.divider()

st.markdown("### Volume Analysis")
high_volume_days = df[df["Volume"] > 1.5 * df["Volume_MA20"].fillna(0)]
volume_fig = go.Figure()
volume_fig.add_trace(go.Bar(
    x=df["Date"], y=df["Volume"], name="Volume",
    marker_color=["rgba(0,200,0,0.6)" if c >= o else "rgba(200,0,0,0.6)" for c, o in zip(df["Close"], df["Open"])]
))
if "Volume_MA20" in df.columns:
    volume_fig.add_trace(go.Scatter(x=df["Date"], y=df["Volume_MA20"], mode="lines", name="20-Day Average", line=dict(color="blue", width=2)))
if not high_volume_days.empty:
    volume_fig.add_trace(go.Scatter(
        x=high_volume_days["Date"], y=high_volume_days["Volume"], mode="markers",
        name="High Volume (>1.5x avg)", marker=dict(symbol="circle", color="orange", size=8, line=dict(color="black", width=1))
    ))
volume_fig.update_layout(height=400, xaxis_title="Date", yaxis_title="Volume", hovermode="x unified")
st.plotly_chart(volume_fig, use_container_width=True)

vol_col1, vol_col2, vol_col3 = st.columns(3)
with vol_col1:
    st.metric("Volume Ratio", f"{vol_ratio:.2f}x" if vol_ratio else "N/A")
with vol_col2:
    st.metric("High Volume Days", len(high_volume_days))
with vol_col3:
    avg_vol = df["Volume"].mean()
    st.metric("Average Volume", f"{avg_vol:,.0f}")

st.divider()

st.markdown("### Technical Indicator Charts")
indicator_tab = st.tabs(["RSI", "MACD", "Stochastic", "ATR / ADR", "Bollinger Bands", "SuperTrend"])

with indicator_tab[0]:
    rsi_fig = go.Figure()
    rsi_fig.add_trace(go.Scatter(x=df["Date"], y=df["RSI"], mode="lines", name="RSI", line=dict(color="purple")))
    rsi_fig.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="Overbought (70)")
    rsi_fig.add_hline(y=30, line_dash="dash", line_color="green", annotation_text="Oversold (30)")
    rsi_fig.add_hrect(y0=70, y1=100, line_width=0, fillcolor="red", opacity=0.1)
    rsi_fig.add_hrect(y0=0, y1=30, line_width=0, fillcolor="green", opacity=0.1)
    rsi_fig.update_layout(height=400, yaxis_range=[0, 100], xaxis_title="Date", yaxis_title="RSI")
    st.plotly_chart(rsi_fig, use_container_width=True)

with indicator_tab[1]:
    macd_fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
    macd_fig.add_trace(go.Scatter(x=df["Date"], y=df["MACD"], mode="lines", name="MACD", line=dict(color="blue")), row=1, col=1)
    macd_fig.add_trace(go.Scatter(x=df["Date"], y=df["MACD_Signal"], mode="lines", name="Signal", line=dict(color="orange")), row=1, col=1)
    macd_fig.add_trace(go.Bar(x=df["Date"], y=df["MACD_Hist"], name="Histogram", marker_color="gray"), row=2, col=1)
    macd_fig.add_hline(y=0, line_dash="dash", line_color="black", row=2, col=1)
    macd_fig.update_layout(height=500, xaxis_title="Date", yaxis_title="MACD", showlegend=True)
    st.plotly_chart(macd_fig, use_container_width=True)

with indicator_tab[2]:
    stoch_fig = go.Figure()
    stoch_fig.add_trace(go.Scatter(x=df["Date"], y=df["Stochastic_K"], mode="lines", name="%K", line=dict(color="blue")))
    stoch_fig.add_trace(go.Scatter(x=df["Date"], y=df["Stochastic_D"], mode="lines", name="%D", line=dict(color="orange")))
    stoch_fig.add_hline(y=80, line_dash="dash", line_color="red")
    stoch_fig.add_hline(y=20, line_dash="dash", line_color="green")
    stoch_fig.update_layout(height=400, yaxis_range=[0, 100], xaxis_title="Date", yaxis_title="Stochastic")
    st.plotly_chart(stoch_fig, use_container_width=True)

with indicator_tab[3]:
    atr_fig = go.Figure()
    atr_fig.add_trace(go.Scatter(x=df["Date"], y=df["ATR"], mode="lines", name="ATR (14)", line=dict(color="red")))
    atr_fig.add_trace(go.Scatter(x=df["Date"], y=df["ADR"], mode="lines", name="ADR (20)", line=dict(color="blue")))
    atr_fig.update_layout(height=400, xaxis_title="Date", yaxis_title="Volatility (%)", hovermode="x unified")
    st.plotly_chart(atr_fig, use_container_width=True)

with indicator_tab[4]:
    bb_fig = go.Figure()
    bb_fig.add_trace(go.Scatter(x=df["Date"], y=df["Close"], mode="lines", name="Close", line=dict(color="black")))
    bb_fig.add_trace(go.Scatter(x=df["Date"], y=df["BB_Upper"], mode="lines", name="Upper Band", line=dict(color="gray", dash="dash")))
    bb_fig.add_trace(go.Scatter(x=df["Date"], y=df["BB_Middle"], mode="lines", name="Middle Band", line=dict(color="blue")))
    bb_fig.add_trace(go.Scatter(x=df["Date"], y=df["BB_Lower"], mode="lines", name="Lower Band", line=dict(color="gray", dash="dash")))
    bb_fig.update_layout(height=400, xaxis_title="Date", yaxis_title="Price", hovermode="x unified")
    st.plotly_chart(bb_fig, use_container_width=True)

with indicator_tab[5]:
    st_fig = go.Figure()
    st_fig.add_trace(go.Scatter(x=df["Date"], y=df["Close"], mode="lines", name="Close", line=dict(color="black")))
    st_fig.add_trace(go.Scatter(x=df["Date"], y=df["SuperTrend_Line"], mode="lines", name="SuperTrend", line=dict(color="green" if df["SuperTrend"].iloc[-1] == 1 else "red")))
    st_fig.update_layout(height=400, xaxis_title="Date", yaxis_title="Price", hovermode="x unified")
    st.plotly_chart(st_fig, use_container_width=True)