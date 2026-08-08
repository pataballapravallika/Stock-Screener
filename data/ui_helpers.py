import streamlit as st
import pandas as pd
from typing import Dict, Any


def render_official_data_header(fund: Dict[str, Any]):
    """Render official source badge, clear-cache button, and metric lineage table."""
    source_type = fund.get("fundamentals_source", "nse_xbrl")
    source_label = "NSE XBRL Integrated Filings" if source_type == "nse_xbrl" else "Official Company Filings"

    col_b1, col_b2 = st.columns([3, 1])
    with col_b1:
        st.success(f"**Data Provenance**: Sourced directly from **{source_label}**. (Zero Yahoo Finance fundamentals)")
    with col_b2:
        if st.button("Refresh Official Data", key=f"refresh_{fund.get('Symbol', 'all')}"):
            st.cache_data.clear()
            st.rerun()

    metric_details = fund.get("metric_details")
    if metric_details and isinstance(metric_details, dict):
        with st.expander("📄 View Official Report Lineage & Source URLs", expanded=False):
            rows = []
            for m_name, det in metric_details.items():
                if not isinstance(det, dict):
                    continue
                val = det.get("value")
                val_str = f"{val:,.2f}" if isinstance(val, (int, float)) else "N/A"
                url = det.get("source_url", "")
                rows.append({
                    "Company": det.get("company"),
                    "Ticker": det.get("ticker"),
                    "Metric": m_name,
                    "Period": det.get("period"),
                    "Qtr/Year": det.get("quarter_or_year"),
                    "Report Date": det.get("report_date"),
                    "Statement Type": "Consolidated" if det.get("consolidated") else "Standalone",
                    "Reported Value": val_str,
                    "Unit": str(det.get("unit") or "N/A"),
                    "Source Type": str(det.get("source_type") or "N/A"),
                    "Official Filing Document": url if url and url != "N/A" else "Official Filing Record",
                })
            if rows:
                df_det = pd.DataFrame(rows)
                st.dataframe(df_det, use_container_width=True, hide_index=True)
