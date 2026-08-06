import yfinance as yf

t = yf.Ticker("RELIANCE.NS")

print("=== Annual financials columns ===")
print("financials columns:", list(t.financials.columns) if t.financials is not None and not t.financials.empty else "None")
print("balance_sheet columns:", list(t.balance_sheet.columns) if t.balance_sheet is not None and not t.balance_sheet.empty else "None")
print("cashflow columns:", list(t.cashflow.columns) if t.cashflow is not None and not t.cashflow.empty else "None")
print("=== Quarterly financials columns ===")
print("quarterly_financials columns:", list(t.quarterly_financials.columns) if t.quarterly_financials is not None and not t.quarterly_financials.empty else "None")
print("=== Info keys ===")
info = t.info
for k in ["returnOnEquity", "returnOnCapitalEmployed", "returnOnAssets", "operatingCashflow", "freeCashFlow", "freeCashFlowPerShare", "totalAssets", "totalDebt", "bookValue", "sharesOutstanding", "totalStockholderEquity", "totalStockholdersEquity"]:
    print(f"  {k}: {info.get(k)}")