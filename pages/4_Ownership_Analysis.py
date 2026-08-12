import streamlit as st
import pandas as pd
import re
import plotly.graph_objects as go
import plotly.express as px
from data.fetch_fundamentals import fetch_fundamentals
from data.providers.yahoo_price_provider import YahooPriceProvider

st.set_page_config(page_title="Ownership Analysis", layout="wide")

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

st.title("Ownership Analysis")
st.caption("FII & DII changes, Mutual Fund holdings, Promoter positions, and Insider trading")

company = st.selectbox("Company", list(COMPANIES.keys()))
symbol = COMPANIES[company]

fund = fetch_fundamentals(symbol) or {}

st.subheader(f"{fund.get('Company') or symbol} — Ownership Analysis")

sector = fund.get("Sector") or "N/A"
industry = fund.get("Industry") or "N/A"
mcap = fund.get("MarketCap")
if not mcap:
    try:
        from data.database import get_company_info as db_get_company_info
        cached = db_get_company_info(symbol)
        if cached and cached.get("market_cap"):
            mcap = float(cached["market_cap"])
    except Exception:
        pass

emp = fund.get("Employees")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Sector", sector)
c2.metric("Industry", industry)
c3.metric("Market Cap", f"₹{mcap:,.0f} Cr" if mcap else "N/A")
c4.metric("Employees", f"{emp:,}" if emp else "N/A")

st.divider()

st.markdown("### Official Shareholding Breakdown")

promoter_val = fund.get("Promoter_Pct")
fii_val = fund.get("FII_Pct")
dii_val = fund.get("DII_Pct")
govt_val = fund.get("Govt_Pct")
public_val = fund.get("Public_Pct")
inst_val = fund.get("Institutional_Pct")
insider_val = fund.get("Promoter_Pct")
shareholders_count = fund.get("Shareholders_Count")
shareholding_period = fund.get("Shareholding_Period")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Promoter %", f"{promoter_val:.2f}%" if promoter_val is not None else "N/A")
c2.metric("FII %", f"{fii_val:.2f}%" if fii_val is not None else "N/A")
c3.metric("DII %", f"{dii_val:.2f}%" if dii_val is not None else "N/A")
c4.metric("Government %", f"{govt_val:.2f}%" if govt_val is not None else "N/A")
c5.metric("Public & Others %", f"{public_val:.2f}%" if public_val is not None else "N/A")

if shareholders_count is not None:
    st.caption(f"Total shareholders: {shareholders_count:,} as of {shareholding_period or 'latest available'}")

labels = []
values = []
chart_colors = ["#636EFA", "#00CC96", "#AB63FA", "#FFA15A", "#19D3F3"]
color_map = {}
color_idx = 0
for name, val in [
    ("Promoters", promoter_val),
    ("FIIs", fii_val),
    ("DIIs", dii_val),
    ("Government", govt_val),
    ("Public & Others", public_val),
]:
    if val is not None and val > 0:
        labels.append(name)
        values.append(val)
        color_map[name] = chart_colors[color_idx % len(chart_colors)]
        color_idx += 1

if values:
    st.write("")
    col_chart, col_table = st.columns([1, 1])

    pie_colors = [color_map.get(name, "#19D3F3") for name in labels]

    with col_chart:
        fig = go.Figure(data=[go.Pie(
            labels=labels,
            values=values,
            hole=0.4,
            marker_colors=pie_colors,
            textinfo="label+percent",
            textfont_size=12,
        )])
        fig.update_layout(
            title="Shareholding Pattern",
            height=360,
            template="plotly_dark",
            showlegend=True,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_table:
        sh_df = pd.DataFrame({
            "Category": labels,
            "Holding (%)": [f"{v:.2f}%" for v in values],
            "Holding (value)": values,
        })
        st.markdown("#### Shareholding Details")
        st.dataframe(sh_df[["Category", "Holding (%)"]], use_container_width=True, hide_index=True)

st.divider()

# ── Quarterly Shareholding Pattern Trend ──────────────────────────────────────
sh_table = fund.get("Shareholding_Table")
sh_history = fund.get("Shareholding_History")

trend_data_present = False
history_df = None

if sh_history and isinstance(sh_history, dict) and sh_history.get("periods"):
    periods = sh_history["periods"]
    trend_rows = []
    for cat in ["Promoters", "FIIs", "DIIs", "Government", "Public"]:
        vals = sh_history.get(cat, [])
        if vals:
            for i, p in enumerate(periods):
                v = vals[i] if i < len(vals) else None
                if v is not None:
                    trend_rows.append({"Period": p, "Category": cat, "Pct": v})
    if trend_rows:
        history_df = pd.DataFrame(trend_rows)
        trend_data_present = True

if not trend_data_present and sh_table is not None and isinstance(sh_table, pd.DataFrame) and not sh_table.empty:
    try:
        df = sh_table.copy()
        if df.shape[1] >= 2:
            first_col = df.columns[0]
            df = df.drop(columns=[first_col]) if first_col in df.columns else df
            periods = [str(c) for c in df.columns]
            trend_rows = []
            cat_map = {
                "promoter": "Promoters",
                "fii": "FIIs",
                "dii": "DIIs",
                "government": "Government",
                "public": "Public",
            }
            for _, row in df.iterrows():
                label_clean = re.sub(r'[^a-zA-Z]', '', str(row.iloc[0])).lower()
                matched_cat = None
                for key, cat_name in cat_map.items():
                    if key in label_clean:
                        matched_cat = cat_name
                        break
                if matched_cat:
                    for i, p in enumerate(periods):
                        val_str = str(row.iloc[i + 1]).replace("%", "").strip()
                        try:
                            v = float(val_str)
                            trend_rows.append({"Period": p, "Category": matched_cat, "Pct": v})
                        except (ValueError, TypeError):
                            pass
            if trend_rows:
                history_df = pd.DataFrame(trend_rows)
                trend_data_present = True
    except Exception:
        pass

if history_df is not None and not history_df.empty:
    st.markdown("### Quarterly Shareholding Pattern Trend")
    fig_trend = px.line(
        history_df,
        x="Period",
        y="Pct",
        color="Category",
        markers=True,
        title="Shareholding % Over Quarters",
        template="plotly_dark",
        color_discrete_sequence=chart_colors,
    )
    fig_trend.update_layout(height=400)
    st.plotly_chart(fig_trend, use_container_width=True)

    st.markdown("#### Quarterly Shareholding Pattern Table")
    pivot_df = history_df.pivot(index="Category", columns="Period", values="Pct")
    if not pivot_df.empty:
        st.dataframe(
            pivot_df.style.format("{:.2f}%"),
            use_container_width=True,
        )

st.divider()

# ── Ownership Summary ─────────────────────────────────────────────────────────
st.markdown("### Ownership Summary")

inst_desc = None
if inst_val is not None:
    if fii_val is not None and dii_val is not None:
        inst_desc = f"Institutional investors (FII {fii_val:.2f}% + DII {dii_val:.2f}%) hold {inst_val:.2f}% of shares outstanding."
    elif fii_val is not None:
        inst_desc = f"Institutional investors (FII {fii_val:.2f}%) hold {inst_val:.2f}% of shares outstanding."
    elif dii_val is not None:
        inst_desc = f"Institutional investors (DII {dii_val:.2f}%) hold {inst_val:.2f}% of shares outstanding."
    else:
        inst_desc = f"Institutional investors hold {inst_val:.2f}% of shares outstanding."
else:
    inst_desc = "Institutional holding data is unavailable from official filings."

promoter_desc = None
if insider_val is not None:
    promoter_desc = f"Promoters/insiders hold {insider_val:.2f}% of shares outstanding."
else:
    promoter_desc = "Promoter holding data is unavailable from official filings."

public_desc = None
if public_val is not None:
    public_desc = f"Public float represents {public_val:.2f}% of shares outstanding."
else:
    public_desc = "Public float data is unavailable from official filings."

ownership_summary = {
    "Institutional Conviction": inst_desc,
    "Promoter Alignment": promoter_desc,
    "Market Liquidity": public_desc,
}
for title, desc in ownership_summary.items():
    with st.expander(title, expanded=True):
        st.write(desc)

st.divider()

# ── Institutional & Mutual Fund Holders ───────────────────────────────────────
st.markdown("### Institutional & Mutual Fund Holders")
price_provider = YahooPriceProvider()

inst_holders = price_provider.get_institutional_holders(symbol)
if inst_holders is not None and not inst_holders.empty:
    display_cols = list(inst_holders.columns)
    if "Date Reported" in display_cols:
        display_cols.remove("Date Reported")
    st.dataframe(inst_holders[display_cols], use_container_width=True, hide_index=True)
else:
    st.info("Institutional holder details unavailable. Official filings (Form 13F for FIIs) are not yet parsed; shareholding data comes from NSE shareholder-pattern disclosures above.")

mf_holders = price_provider.get_mutual_fund_holders(symbol)
if mf_holders is not None and not mf_holders.empty:
    st.markdown("#### Top Mutual Fund Holders")
    display_cols = list(mf_holders.columns)
    if "Date Reported" in display_cols:
        display_cols.remove("Date Reported")
    st.dataframe(mf_holders[display_cols], use_container_width=True, hide_index=True)
else:
    st.info("Mutual fund holder details unavailable. MFs typically report via NSE quarterly shareholding patterns where they appear under the 'Public' or 'FIIs' category.")

st.divider()

# ── Insider Trading ───────────────────────────────────────────────────────────
st.markdown("### Insider Trading")
insider_txns = price_provider.get_insider_transactions(symbol)
if insider_txns is not None and not insider_txns.empty:
    display_cols = list(insider_txns.columns)
    if "Date" in display_cols:
        display_cols.remove("Date")
    st.dataframe(insider_txns[display_cols], use_container_width=True, hide_index=True)
else:
    st.info("Insider trading details unavailable. Indian promoters report shareholding changes through NSE shareholder-pattern filings (quarterly SHP), reflected in the shareholding breakdown above.")

insider_roster = price_provider.get_insider_roster(symbol)
if insider_roster is not None and not insider_roster.empty:
    st.write("")
    st.markdown("#### Insider Roster (Officers & Directors)")
    st.dataframe(insider_roster, use_container_width=True, hide_index=True)

insider_purchases = price_provider.get_insider_purchases(symbol)
if insider_purchases is not None and not insider_purchases.empty:
    st.write("")
    st.markdown("#### Recent Insider Purchases/Sales")
    st.dataframe(insider_purchases, use_container_width=True, hide_index=True)

st.divider()

# ── Major Holders Breakdown ───────────────────────────────────────────────────
st.markdown("### Major Holders Breakdown")
major_holders = price_provider.get_major_holders(symbol)
if major_holders is not None and not major_holders.empty:
    mh_df = major_holders.copy()
    mh_df.columns = [str(c).strip() for c in mh_df.columns]
    st.dataframe(mh_df, use_container_width=True, hide_index=True)
else:
    st.info("Major holders breakdown unavailable from official sources.")
