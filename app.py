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
            "pages/1_Dashboard.py",
            title="Dashboard"
        ),

        st.Page(
            "pages/2_Growth_Analysis.py",
            title="Growth Analysis"
        ),

        st.Page(
            "pages/3_Quality_Analysis.py",
            title="Quality Analysis"
        ),

        st.Page(
            "pages/4_Ownership_Analysis.py",
            title="Ownership Analysis"
        ),

        st.Page(
            "pages/5_Technical_Analysis.py",
            title="Technical Analysis"
        ),

        st.Page(
            "pages/6_Valuation.py",
            title="Valuation"
        ),

        st.Page(
            "pages/7_Catalysts.py",
            title="Catalysts"
        ),

        st.Page(
            "pages/8_Backtesting.py",
            title="Backtesting"
        ),

        st.Page(
            "pages/9_Portfolio_Risk.py",
            title="Portfolio & Risk"
        ),

        st.Page(
            "pages/10_Sector_Rotation.py",
            title="Sector Analysis"
        ),

        st.Page(
            "pages/11_Ranking_Engine.py",
            title="Ranking Engine"
        ),

        st.Page(
            "pages/12_Alerts_AI.py",
            title="Alerts & AI Research"
        ),
    ]
}

navigation = st.navigation(pages)

navigation.run()