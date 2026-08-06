from data.fetch_fundamentals import fetch_fundamentals
from data.fetch_utils import get_quarterly_df, quarterly_eps_series
from fundamentals.growth import calculate_growth_metrics, safe_float
import pandas as pd

SYMBOL = "RELIANCE.NS"

print(f"Validating {SYMBOL}\n{'='*40}")
fund = fetch_fundamentals(SYMBOL)
print("Fundamentals source:", fund.get("fundamentals_source"))
print("Quarterly metadata:", fund.get("quarterly_meta"))

# Raw info-derived values
info_fields = [
    "PE", "ForwardPE", "PriceSales", "ROE", "ROCE", "ROA", "DebtEquity",
    "RevenueGrowth", "EarningsGrowth", "EarningsQuarterlyGrowth", "ProfitMargin",
    "OperatingCashFlow", "TotalCash", "EnterpriseValue"
]
print("\nInfo-derived fields:")
for field in info_fields:
    print(f" {field}: {fund.get(field)!r}")

q_df = get_quarterly_df(fund)
print("\nQuarterly DataFrame available:", q_df is not None)
if q_df is not None:
    print("Quarterly columns:", list(q_df.columns))
    print("Quarterly index:", list(q_df.index))
    for label in ["Total Revenue", "Revenue", "Sales", "Operating Revenue", "Net Income", "Net Income Common Stockholders", "EBIT", "Operating Income", "Diluted EPS", "Basic EPS", "EPS"]:
        if label in q_df.index:
            values = [safe_float(q_df.loc[label, c]) for c in q_df.columns]
            print(f" {label}: {values}")

# EPS label origin
eps_label = None
if q_df is not None:
    for label in ["Diluted EPS", "Basic EPS", "EPS"]:
        if label in q_df.index:
            eps_label = label
            break
print("\nQuarterly EPS label:", eps_label)
if eps_label and q_df is not None:
    eps_values = [safe_float(q_df.loc[eps_label, c]) for c in q_df.columns]
    print(" Quarterly EPS values:", eps_values)
    print(" Quarterly EPS periods:", [str(c) for c in q_df.columns])
else:
    print(" Quarterly EPS not found in quarterly financials.")

# Compute quarterly metrics from quarterly financials
if q_df is not None:
    q_metrics = calculate_growth_metrics(q_df, quarterly=True)
    print("\nCalculated quarterly metrics from provider q_df:")
    for k in sorted(q_metrics.keys()):
        print(f" {k}: {q_metrics[k]}")

print("\nChecking quarterly EPS origin: always from q_df, not info")
print(" q_df is used for quarterly metrics in pages 5 and 2 if available.")

# Annual metrics from yfinance statements
try:
    import yfinance as yf
    t = yf.Ticker(SYMBOL)
    inc = getattr(t, 'income_stmt', None)
    bs = getattr(t, 'balance_sheet', None)
    cf = getattr(t, 'cashflow', None)
    print("\nRaw annual income statement available:", inc is not None and not inc.empty)
    if inc is not None and not inc.empty:
        print("Income statement columns:", list(inc.columns))
        for label in ["Net Income", "Total Revenue", "EBIT", "Operating Income", "Diluted EPS", "Basic EPS", "EPS"]:
            if label in inc.index:
                print(f" {label}: {[safe_float(inc.loc[label, c]) for c in inc.columns]}")
    print("\nRaw balance sheet available:", bs is not None and not bs.empty)
    if bs is not None and not bs.empty:
        print("Balance sheet columns:", list(bs.columns))
        for label in ["Total Assets", "Total Debt", "Stockholders Equity", "Total Equity", "Current Assets", "Current Liabilities"]:
            if label in bs.index:
                print(f" {label}: {[safe_float(bs.loc[label, c]) for c in bs.columns]}")
    print("\nRaw cashflow available:", cf is not None and not cf.empty)
    if cf is not None and not cf.empty:
        print("Cashflow columns:", list(cf.columns))
        for label in ["Operating Cash Flow", "Net Cash from Operating Activities"]:
            if label in cf.index:
                print(f" {label}: {[safe_float(cf.loc[label, c]) for c in cf.columns]}")
except Exception as e:
    print("Error loading raw yfinance annual statements:", e)

print("\nDone.")
