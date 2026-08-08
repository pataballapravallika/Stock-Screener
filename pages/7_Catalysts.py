import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from data.fetch_fundamentals import fetch_fundamentals
from data.fetch_prices import fetch_prices

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
ticker = yf.Ticker(symbol)

company_name = fund.get("Company") or symbol
sector = fund.get("Sector") or "Technology"
industry = fund.get("Industry") or "IT Services"

mcap = fund.get("MarketCap")
if not mcap:
    try:
        fi = getattr(ticker, "fast_info", {})
        mc = fi.get("marketCap") or (ticker.info.get("marketCap") if hasattr(ticker, "info") else None)
        if mc:
            mcap = mc / 1e7
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
    calendar = ticker.calendar
    if calendar is not None and not calendar.empty:
        cal_rows = []
        if isinstance(calendar, pd.DataFrame):
            for idx in calendar.index:
                val = calendar.loc[idx].iloc[0] if not calendar.loc[idx].empty else "N/A"
                cal_rows.append({"Event": str(idx), "Date": str(val)})
        elif isinstance(calendar, dict):
            for k, v in calendar.items():
                cal_rows.append({"Event": str(k), "Date": str(v)})

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
try:
    raw_news = ticker.news
    if raw_news and len(raw_news) > 0:
        for item in raw_news[:10]:
            cnt = item.get("content") if isinstance(item.get("content"), dict) else item
            title = cnt.get("title") or item.get("title") or "No title"
            summary = cnt.get("summary") or cnt.get("description") or ""

            prov = cnt.get("provider") if isinstance(cnt.get("provider"), dict) else item.get("publisher")
            pub_name = "Unknown"
            if isinstance(prov, dict):
                pub_name = prov.get("displayName") or prov.get("name") or "Unknown"
            elif isinstance(prov, str):
                pub_name = prov

            pub_date = cnt.get("pubDate") or cnt.get("published") or item.get("published")
            date_str = "N/A"
            if pub_date:
                try:
                    dt = datetime.fromisoformat(str(pub_date).replace("Z", "+00:00"))
                    date_str = dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    date_str = str(pub_date)[:10]
            elif item.get("providerPublishTime"):
                try:
                    dt = datetime.fromtimestamp(item["providerPublishTime"])
                    date_str = dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass

            canon = cnt.get("canonicalUrl") if isinstance(cnt.get("canonicalUrl"), dict) else {}
            click = cnt.get("clickThroughUrl") if isinstance(cnt.get("clickThroughUrl"), dict) else {}
            link = canon.get("url") or click.get("url") or item.get("link") or ""

            with st.expander(f"{title} ({date_str})", expanded=False):
                st.caption(f"Source: {pub_name}")
                if summary:
                    st.write(summary)
                if link:
                    st.markdown(f"[Read full article →]({link})")
    else:
        st.info("News data unavailable for this ticker.")
except Exception:
    st.info("News data unavailable.")

st.divider()

st.markdown("### Dividend History")
try:
    dividends = ticker.dividends
    if dividends is not None and not dividends.empty:
        div_df = dividends.reset_index()
        div_df.columns = ["Date", "Dividend"]
        div_df["Dividend"] = div_df["Dividend"].apply(lambda x: f"₹{x:.4f}" if pd.notna(x) else "N/A")
        st.dataframe(div_df.tail(12), use_container_width=True, hide_index=True)
    else:
        st.info("Dividend history unavailable.")
except Exception:
    st.info("Dividend history unavailable.")

st.divider()

st.markdown("### Stock Split History")
try:
    splits = ticker.splits
    if splits is not None and not splits.empty:
        split_df = splits.reset_index()
        split_df.columns = ["Date", "Split Ratio"]
        st.dataframe(split_df, use_container_width=True, hide_index=True)
    else:
        st.info("No stock splits recorded.")
except Exception:
    st.info("Stock split data unavailable.")