import yfinance as yf
import pandas as pd

t = yf.Ticker("RELIANCE.NS")

print("=== Annual income statement ===")
inc = t.financials
if inc is not None and not inc.empty:
    print("Shape:", inc.shape)
    print("Columns:", list(inc.columns))
    print("Index:", list(inc.index))
    for label in ["Net Income", "Total Revenue", "EBIT", "Operating Income", "Diluted EPS", "Basic EPS", "EPS"]:
        if label in inc.index:
            print(f" {label}: {inc.loc[label].tolist()}")
else:
    print("None or empty")

print("\n=== Annual balance sheet ===")
bs = t.balance_sheet
if bs is not None and not bs.empty:
    print("Shape:", bs.shape)
    print("Columns:", list(bs.columns))
    print("Index:", list(bs.index))
    for label in ["Total Assets", "Total Debt", "Stockholders Equity", "Total Equity", "Total Shareholders Equity", "Total Stockholder Equity", "Current Assets", "Current Liabilities", "Working Capital", "Retained Earnings"]:
        if label in bs.index:
            print(f" {label}: {bs.loc[label].tolist()}")
else:
    print("None or empty")

print("\n=== Annual cashflow ===")
cf = t.cashflow
if cf is not None and not cf.empty:
    print("Shape:", cf.shape)
    print("Columns:", list(cf.columns))
    print("Index:", list(cf.index))
    for label in ["Operating Cash Flow", "Net Cash from Operating Activities", "Capital Expenditures", "CapEx", "Capital Expenditure", "Free Cash Flow", "Net Cash from Investing", "Net Cash from Financing"]:
        if label in cf.index:
            print(f" {label}: {cf.loc[label].tolist()}")
else:
    print("None or empty")

print("\n=== Quarterly income statement ===")
qinc = t.quarterly_financials
if qinc is not None and not qinc.empty:
    print("Shape:", qinc.shape)
    print("Columns:", list(qinc.columns))
    print("Index:", list(qinc.index))
    for label in ["Net Income", "Total Revenue", "EBIT", "Operating Income", "Diluted EPS", "Basic EPS", "EPS"]:
        if label in qinc.index:
            vals = [qinc.loc[label, c] for c in qinc.columns]
            print(f" {label}: {vals}")
else:
    print("None or empty")