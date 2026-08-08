from nse_xbrl import NSEClient
import requests

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

client = NSEClient(cookie_string=cookie_str)
filings = client.fetch_financials('HDFCBANK', 'HDFC Bank Limited', max_filings=5)
print('Filings:', len(filings))
for f in filings[:3]:
    print(f'  period: {f.period_start} -> {f.period_end}')
    print(f'  is_consolidated: {f.is_consolidated}, is_audited: {f.is_audited}')
    print(f'  q_revenue: {f.q_revenue}, ytd_revenue: {f.ytd_revenue}')
    print(f'  q_pat: {f.q_pat}, ytd_pat: {f.ytd_pat}')
    print(f'  q_diluted_eps: {f.q_diluted_eps}, ytd_diluted_eps: {f.ytd_diluted_eps}')
    print(f'  bs_total_assets: {f.bs_total_assets}, bs_equity: {f.bs_equity}')
    print(f'  bs_current_assets: {f.bs_current_assets}, bs_current_liabilities: {f.bs_current_liabilities}')
    print(f'  raw_facts keys: {list(f.raw_facts.keys())[:30]}')
    print()

# Also check: for banks, the income might be called different things
f = filings[0] if filings else None
if f and f.raw_facts:
    # Look for bank-specific tags
    for tag in f.raw_facts:
        if any(word in tag.lower() for word in ['income', 'revenue', 'netinterest', 'profit', 'loss', 'assets', 'liabilities', 'equity', 'deposits', 'borrowings']):
            val = f.raw_facts[tag]
            print(f'  {tag}: {val}')
