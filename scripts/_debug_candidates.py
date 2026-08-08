"""Debug _fetch_screener_tables income candidates."""
import sys
sys.path.insert(0, ".")
import re
import pandas as pd
from bs4 import BeautifulSoup
import requests
from io import StringIO
from data.providers.official_reports_provider import OfficialReportsProvider

p = OfficialReportsProvider()

for ticker in ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "SBIN.NS"]:
    slug = p._ticker_to_slug(ticker)
    html = p._get(f"{p.BASE_URL}/company/{slug}/consolidated/")
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    print(f"\n=== {ticker} ===")
    income_candidates = []
    for i, table in enumerate(tables):
        try:
            dfs = pd.read_html(StringIO(str(table)))
            if not dfs:
                continue
            df = dfs[0]
            if df.empty or len(df.columns) < 2:
                continue
            df = df.set_index(df.columns[0])
            index_labels = [str(idx).lower().strip() for idx in df.index]
            q_match = p._looks_like_quarterly_income(df, index_labels)
            a_match = p._looks_like_annual_income(df, index_labels)
            bs_match = p._looks_like_balance_sheet(index_labels)
            cf_match = p._looks_like_cashflow(index_labels)
            if q_match or a_match:
                is_ann = p._has_fy_columns(df)
                is_q = p._has_quarter_columns(df)
                print(f"  Table {i}: income rows={len(df)} cols={len(df.columns)} q={q_match} a={a_match} is_fy={is_ann} is_q={is_q}")
                print(f"    Cols: {list(df.columns)}")
                income_candidates.append((i, len(df), len(df.columns), q_match, a_match, is_ann, is_q))
        except Exception as e:
            pass

    print(f"  Income candidates: {len(income_candidates)}")
    for ic in income_candidates:
        print(f"    Table {ic[0]}: rows={ic[1]}, cols={ic[2]}, q={ic[3]}, a={ic[4]}, fy={ic[5]}, q_cols={ic[6]}")
