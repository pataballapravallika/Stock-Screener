import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from data.fetch_fundamentals import fetch_fundamentals
from data.fetch_prices import fetch_prices
from data.database import get_latest_quarterly_reports

st.set_page_config(page_title="Catalysts", layout="wide")

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

CATALYST_TYPES = [
    "Order Wins / Book",
    "Product Launches",
    "Earnings Surprise",
    "Expansion",
    "New Product Launch",
    "New Establishment",
    "Regulatory Approval",
    "Capex Announcement",
]

st.title("Catalysts & Events")
st.caption("Upcoming earnings, order wins, product launches, and corporate actions")

company = st.selectbox("Company", list(COMPANIES.keys()))
symbol = COMPANIES[company]

fund = fetch_fundamentals(symbol) or {}

company_name = fund.get("Company") or symbol
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

st.subheader(f"{company_name} — Catalysts")

c1, c2, c3 = st.columns(3)
c1.metric("Sector", sector)
c2.metric("Industry", industry)
c3.metric("Market Cap", f"₹{mcap:,.0f} Cr" if mcap else "N/A")

st.divider()

st.markdown("### Earnings & Dividend Calendar")
try:
    q_df = get_latest_quarterly_reports(symbol, n=8)
    if not q_df.empty:
        cal_rows = []
        for _, row in q_df.iterrows():
            rd = row.get("report_date", "")
            q = row.get("quarter", 1)
            fy = row.get("financial_year", "")
            period = row.get("period", "")
            cal_rows.append({
                "Event": f"Q{q} FY{fy} Results",
                "Date": rd,
            })
        if cal_rows:
            cal_df = pd.DataFrame(cal_rows)
            st.dataframe(cal_df, use_container_width=True, hide_index=True)
        else:
            st.caption("No upcoming calendar events scheduled.")
    else:
        st.caption("Calendar data not available.")
except Exception:
    st.caption("Calendar data not available through current data provider.")

st.divider()

st.markdown("### Upcoming Catalysts")

catalyst_data = [
    {"Catalyst": "Earnings Announcement", "Expected": "Next quarterly report", "Impact": "High", "Category": "Earnings Surprise"},
    {"Catalyst": "Quarterly Results", "Expected": "Next earnings season", "Impact": "High", "Category": "Earnings Surprise"},
    {"Catalyst": "Dividend Declaration", "Expected": "Next ex-date", "Impact": "Medium", "Category": "Order Wins / Book"},
    {"Catalyst": "Board Meeting", "Expected": "Next quarterly meeting", "Impact": "Medium", "Category": "New Establishment"},
    {"Catalyst": "Product Launch", "Expected": "TBD", "Impact": "Medium", "Category": "Product Launches"},
    {"Catalyst": "Capacity Expansion", "Expected": "TBD", "Impact": "Medium", "Category": "Expansion"},
    {"Catalyst": "Regulatory Filing", "Expected": "TBD", "Impact": "Low", "Category": "Regulatory Approval"},
    {"Catalyst": "Capex Update", "Expected": "Next annual report", "Impact": "Medium", "Category": "Capex Announcement"},
]

cat_df = pd.DataFrame(catalyst_data)
st.dataframe(cat_df, use_container_width=True, hide_index=True)

st.divider()

st.markdown("### Catalyst Filters")
selected_types = st.multiselect("Filter by Category", CATALYST_TYPES, default=CATALYST_TYPES)

filtered = cat_df[cat_df["Category"].isin(selected_types)]
if not filtered.empty:
    st.dataframe(filtered, use_container_width=True, hide_index=True)

st.divider()

st.markdown("### Historical Catalyst Impact")
st.caption("Past catalyst events and their impact on stock price (based on available data)")

try:
    hist_df = fetch_prices(symbol, period="6mo")
    if not hist_df.empty and len(hist_df) > 10:
        hist_df["Return"] = hist_df["Close"].pct_change() * 100
        hist_df["Abs_Return"] = hist_df["Return"].abs()

        high_impact_days = hist_df.nlargest(5, "Abs_Return")
        if not high_impact_days.empty:
            st.subheader("Largest Price Moves (6 Months)")
            impact_df = high_impact_days[["Date", "Close", "Return"]].copy()
            impact_df["Date"] = impact_df["Date"].dt.strftime("%Y-%m-%d")
            impact_df.columns = ["Date", "Close (₹)", "Daily Return (%)"]
            st.dataframe(impact_df, use_container_width=True, hide_index=True)
except Exception:
    st.caption("Historical catalyst impact data not available.")

st.divider()

st.markdown("### Catalyst Summary")
catalyst_summary = {
    "Order Wins / Book": "New contract wins or order book expansions signal growing demand and revenue visibility.",
    "Product Launches": "New products or services can drive revenue growth and market share gains.",
    "Earnings Surprise": "Beating or missing consensus estimates creates short-term price momentum.",
    "Expansion": "Capacity additions or geographic expansion signal long-term growth potential.",
    "New Product Launch": "Innovation-driven launches can create new revenue streams.",
    "New Establishment": "New facilities or subsidiaries indicate growth ambitions.",
    "Regulatory Approval": "Approvals for new products, markets, or operations remove uncertainty.",
    "Capex Announcement": "Capital expenditure plans signal management confidence in future growth.",
}
for cat, desc in catalyst_summary.items():
    with st.expander(cat):
        st.write(desc)

st.divider()

st.markdown("### Recent News & Announcements")
st.info("News data is not available from official NSE filings within this module. Please refer to the company's investor relations page for announcements.")

st.divider()

st.markdown("### Dividend History")
st.info("Dividend history is sourced from official NSE company filings. Please refer to the company's annual reports for dividend declarations.")

st.divider()

st.markdown("### Stock Split History")
st.info("Stock split data is not available from official NSE filings within this module.")