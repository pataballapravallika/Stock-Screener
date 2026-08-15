import streamlit as st
import pandas as pd
from typing import Dict, Any


def render_official_data_header(fund: Dict[str, Any]):
    """Render official source badge, clear-cache button, and metric lineage table."""
    source_type = fund.get("fundamentals_source", "nse_xbrl")
    verification = fund.get("data_verification_status", "not_verified")
    nse_blocked = fund.get("nse_access_blocked", False)

    if source_type == "nse_xbrl":
        source_label = "NSE XBRL Integrated Filings"
    else:
        source_label = "Official Company Reports"

    if verification == "verified" and not nse_blocked:
        provenance = f"**VERIFIED OFFICIAL DATA** — Sourced directly from {source_label}."
        status_color = "success"
    elif verification == "verified" and nse_blocked:
        provenance = f"**CACHED VERIFIED OFFICIAL DATA** — From {source_label}. NSE currently returning HTTP 403 (Akamai). Using last verified filing."
        status_color = "warning"
    else:
        provenance = "**N/A / NOT VERIFIED** — No official NSE filing could be retrieved (HTTP 403). No third-party fallback used."
        status_color = "error"

    col_b1, col_b2 = st.columns([3, 1])
    with col_b1:
        if status_color == "success":
            st.success(provenance)
        elif status_color == "warning":
            st.warning(provenance)
        else:
            st.error(provenance)
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
