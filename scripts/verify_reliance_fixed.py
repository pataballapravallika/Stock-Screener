import sys
sys.path.insert(0, r'D:\career-projects\Stock_Screener')

from data.fetch_fundamentals import fetch_fundamentals
import yfinance as yf

symbol = "RELIANCE.NS"
print(f"=== Verifying {symbol} ===")

fund = fetch_fundamentals(symbol)
print(f"\nCompany: {fund.get('Company')}")
print(f"Sector: {fund.get('Sector')}")

print("\n--- Key Metrics ---")
print(f"ROE: {fund.get('ROE')}")
print(f"ROCE: {fund.get('ROCE')}")
print(f"ROA: {fund.get('ROA')}")
print(f"OperatingCashFlowTTM: {fund.get('OperatingCashFlowTTM')}")
print(f"OperatingCashFlowAnnual: {fund.get('OperatingCashFlowAnnual')}")
print(f"FreeCashFlowTTM: {fund.get('FreeCashFlowTTM')}")
print(f"FreeCashFlowAnnual: {fund.get('FreeCashFlowAnnual')}")
print(f"FreeCashFlow: {fund.get('FreeCashFlow')}")
print(f"NetIncome: {fund.get('NetIncome')}")
print(f"TotalAssets: {fund.get('TotalAssets')}")
print(f"TotalDebt: {fund.get('TotalDebt')}")
print(f"ShareholdersEquity (computed): {fund.get('SharesOutstanding') * fund.get('BookValue') if fund.get('SharesOutstanding') and fund.get('BookValue') else 'N/A'}")

print("\n--- Cross-check with yfinance annual statements ---")
ticker = yf.Ticker(symbol)

# ROE check
ni = None
se = None
ta = None
ebit = None
cf_ocf = None
cf_fcf = None
cf_capex = None

inc = ticker.financials
bs = ticker.balance_sheet
cf = ticker.cashflow

if inc is not None and not inc.empty:
    for label in ["Net Income", "Net Income Common Stockholders"]:
        if label in inc.index:
            ni = inc.loc[label, inc.columns[0]]
            break
    for label in ["EBIT", "Operating Income"]:
        if label in inc.index:
            ebit = inc.loc[label, inc.columns[0]]
            break

if bs is not None and not bs.empty:
    for label in ["Stockholders Equity", "Total Equity", "Total Stockholder Equity"]:
        if label in bs.index:
            se = bs.loc[label, bs.columns[0]]
            break
    for label in ["Total Assets", "Assets"]:
        if label in bs.index:
            ta = bs.loc[label, bs.columns[0]]
            break

if cf is not None and not cf.empty:
    for label in ["Operating Cash Flow", "Net Cash from Operating Activities"]:
        if label in cf.index:
            cf_ocf = cf.loc[label, cf.columns[0]]
            break
    for label in ["Free Cash Flow"]:
        if label in cf.index:
            cf_fcf = cf.loc[label, cf.columns[0]]
            break
    for label in ["Capital Expenditure", "CapEx"]:
        if label in cf.index:
            cf_capex = cf.loc[label, cf.columns[0]]
            break

print(f"Annual Net Income: {ni}")
print(f"Annual Shareholders Equity: {se}")
print(f"Annual Total Assets: {ta}")
print(f"Annual EBIT: {ebit}")
print(f"Annual OCF: {cf_ocf}")
print(f"Annual FCF (from cashflow statement): {cf_fcf}")
print(f"Annual CapEx: {cf_capex}")

if ni is not None and se is not None and se != 0:
    computed_roe = ni / se
    print(f"\nComputed ROE = {ni} / {se} = {computed_roe:.6f} ({computed_roe*100:.2f}%)")
    print(f"Fetch fundamentals ROE = {fund.get('ROE')}")

if ebit is not None and ta is not None and se is not None:
    cape = ta - se
    computed_roce = ebit / cape if cape != 0 else None
    print(f"Computed ROCE = {ebit} / ({ta} - {se}) = {computed_roce:.6f} ({computed_roce*100:.2f}%)" if computed_roce else "Cannot compute ROCE")
    print(f"Fetch fundamentals ROCE = {fund.get('ROCE')}")

if ni is not None and ta is not None and ta != 0:
    computed_roa = ni / ta
    print(f"Computed ROA = {ni} / {ta} = {computed_roa:.6f} ({computed_roa*100:.2f}%)")
    print(f"Fetch fundamentals ROA = {fund.get('ROA')}")

if cf_ocf is not None and cf_capex is not None:
    computed_fcf = cf_ocf + cf_capex
    print(f"\nComputed FCF = {cf_ocf} + ({cf_capex}) = {computed_fcf}")
    print(f"Fetch fundamentals FCF Annual = {fund.get('FreeCashFlowAnnual')}")
    print(f"Fetch fundamentals FCF (from cashflow statement) = {cf_fcf}")

print("\n=== Verification Complete ===")