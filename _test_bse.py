import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from data.providers.nse_xbrl_provider import NSEXBRLProvider

provider = NSEXBRLProvider()
# Call _fetch_filings_nsexbrl directly
filings = provider._fetch_filings_nsexbrl("HDFCBANK", "HDFC Bank Limited", max_filings=3)
print(f"Filings: {len(filings)}")
for f in filings:
    print(f"  period_end={f.period_end}, is_consolidated={f.is_consolidated}")
    print(f"  bs_total_assets={getattr(f, 'bs_total_assets', 'NOT SET')}")
    print(f"  total_assets={getattr(f, 'total_assets', 'NOT SET')}")
    print(f"  bs_equity={getattr(f, 'bs_equity', 'NOT SET')}")
    print(f"  bs_total_liabilities={getattr(f, 'bs_total_liabilities', 'NOT SET')}")
    print(f"  total_debt={getattr(f, 'total_debt', 'NOT SET')}")
    print(f"  q_revenue={getattr(f, 'q_revenue', 'NOT SET')}")
    print(f"  q_pat={getattr(f, 'q_pat', 'NOT SET')}")
    print()
