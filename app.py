import streamlit as st

st.set_page_config(
    page_title="Stock Screener",
    page_icon="📈",
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
    ]
}

navigation = st.navigation(pages)

navigation.run()