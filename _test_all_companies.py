from nse_xbrl import NSEClient
import requests, json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
}
session = requests.Session()
session.headers.update(headers)
session.get('https://www.nseindia.com/', timeout=15)
cookie_str = '; '.join(f'{k}={v}' for k, v in session.cookies.items())

# Test with different tickers
for symbol, issuer in [('TCS', 'Tata Consultancy Services Limited'), ('INFY', 'Infosys Limited'), ('HDFCBANK', 'HDFC Bank Limited'), ('SBIN', 'State Bank of India')]:
    try:
        client = NSEClient(cookie_string=cookie_str)
        filings = client.fetch_financials(symbol, issuer, max_filings=2)
        if filings:
            f = filings[0]
            print(f'{symbol}: company={f.company_name}, q_revenue={f.q_revenue}, q_pat={f.q_pat}, q_diluted_eps={f.q_diluted_eps}')
            print(f'  bs_equity={f.bs_equity}, bs_total_assets={f.bs_total_assets}, bs_total_liabilities={f.bs_total_liabilities}')
            print(f'  bs_current_assets={f.bs_current_assets}, bs_current_liabilities={f.bs_current_liabilities}')
            print(f'  cf_capex={f.cf_capex}, paid_up_equity={f.paid_up_equity}, face_value={f.face_value}')
            print(f'  is_consolidated={f.is_consolidated}, is_audited={f.is_audited}')
            print(f'  debt_equity_ratio={f.debt_equity_ratio}')
            print()
        else:
            print(f'{symbol}: No filings')
    except Exception as e:
        print(f'{symbol}: ERROR - {e}')
    print()
