import streamlit as st

st.set_page_config(
    page_title="Stock Screener",
    layout="wide",
    initial_sidebar_state="expanded"
)

pages = {
    "Stock Screener": [
        st.Page(
            "home.py",
            title="Home"
        ),

        st.Page(
            "pages/1_Market_Overview.py",
            title="Market Overview"
        ),

        st.Page(
            "pages/2_Stock_Analysis.py",
            title="Stock Analysis"
        ),

        st.Page(
            "pages/3_Screener.py",
            title="Screener"
        ),

        st.Page(
            "pages/4_Backtesting.py",
            title="Backtesting"
        ),

        st.Page(
            "pages/5_Fundamentals.py",
            title="Fundamentals"
        ),
        st.Page(
            "pages/6_Sector_Dashboard.py",
            title="Sector Dashboard"
        ),
        st.Page(
            "pages/6_Quarterly_Ranking.py",
            title="Quarterly Ranking"
        ),
        st.Page(
            "pages/7_Sector_Analysis.py",
            title="Sector Analysis"
        ),
    ]
}

navigation = st.navigation(pages)

navigation.run()