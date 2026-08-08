import sys
sys.path.insert(0, r"D:\career-projects\Stock_Screener")

from data.providers.official_reports_provider import OfficialReportsProvider, ReportParser
import pandas as pd

provider = OfficialReportsProvider()
q_income, _, _, _ = provider._fetch_screener_tables("RELIANCE.NS")

print(f"q_income is None: {q_income is None}")
if q_income is not None:
    print(f"q_income shape: {q_income.shape}")
    print(f"q_income columns (before normalize): {list(q_income.columns)}")
    print(f"q_income index (before normalize): {list(q_income.index)}")
    
    q_income = provider._normalize_periods(q_income)
    print(f"q_income columns (after normalize): {list(q_income.columns)}")
    
    q_income = provider._normalize_labels(q_income, provider.INCOME_LABEL_RENAME)
    print(f"q_income index (after normalize): {list(q_income.index)}")
    
    col = q_income.columns[0]
    print(f"\nTesting extraction for column: {col}")
    for metric in ["revenue", "operating_profit", "ebit", "pat", "eps"]:
        val = ReportParser.extract_income_value(q_income, metric, col)
        print(f"  {metric}: {val}")
    
    # Also test direct df.loc access
    print(f"\nDirect access test:")
    for metric in ["revenue", "operating_profit", "ebit", "pat", "eps"]:
        label_map = {
            "revenue": ["Total Revenue", "Revenue", "Sales", "Operating Revenue", "Total Sales", "Revenue from Operations"],
            "operating_profit": ["Operating Profit", "EBIT", "Operating Income", "Profit Before Interest And Tax"],
            "ebit": ["EBIT", "Operating Income", "Operating Profit", "Profit Before Interest And Tax"],
            "pat": ["Net Profit", "Net Income", "Profit After Tax", "Net Profit After Tax", "Profit For The Period", "PAT"],
            "eps": ["EPS in Rs", "Diluted EPS", "Basic EPS", "EPS", "Earnings Per Share"],
        }
        candidates = label_map.get(metric, [])
        found_label = None
        for candidate in candidates:
            for idx_label in q_income.index:
                if candidate.lower() in str(idx_label).lower():
                    found_label = idx_label
                    break
            if found_label:
                break
        if found_label:
            try:
                raw = q_income.loc[found_label, col]
                print(f"  {metric}: label='{found_label}', raw='{raw}', type={type(raw)}")
            except Exception as e:
                print(f"  {metric}: label='{found_label}', ERROR={e}")
        else:
            print(f"  {metric}: NOT FOUND in index {list(q_income.index)}")
