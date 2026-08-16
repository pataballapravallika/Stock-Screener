"""Verification script to test that all universe stock tickers return full, non-N/A metrics.

Simulates deployment mode where live scraping is unavailable or blocked.
"""

from data.fetch_fundamentals import fetch_fundamentals, clear_fundamentals_cache

SYMBOLS = [
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "TATAMOTORS",
    "ITC",
    "WIPRO",
    "HCLTECH",
    "NTPC",
    "POWERGRID",
    "ONGC",
]

def verify():
    clear_fundamentals_cache()
    failures = []
    print("================================================================")
    print(" VERIFYING FUNDAMENTAL DATA & METRICS FOR DEPLOYMENT")
    print("================================================================\n")

    for s in SYMBOLS:
        fund = fetch_fundamentals(s)
        company = fund.get("Company") or fund.get("company_name")
        sector = fund.get("Sector")
        industry = fund.get("Industry")
        mcap = fund.get("MarketCap")
        pe = fund.get("PE")
        eps = fund.get("EPS")
        rev = fund.get("Revenue")
        pat = fund.get("PAT")
        roe = fund.get("ROE")
        roce = fund.get("ROCE")
        promoter = fund.get("Promoter_Pct")
        fii = fund.get("FII_Pct")
        dii = fund.get("DII_Pct")
        public = fund.get("Public_Pct")

        missing = []
        if not sector or sector == "N/A":
            missing.append("Sector")
        if not industry or industry == "N/A":
            missing.append("Industry")
        if mcap is None:
            missing.append("MarketCap")
        if pe is None:
            missing.append("PE")
        if eps is None:
            missing.append("EPS")
        if rev is None:
            missing.append("Revenue")
        if pat is None:
            missing.append("PAT")
        if roe is None:
            missing.append("ROE")

        status = "PASSED" if not missing else f"FAILED (Missing: {', '.join(missing)})"
        if missing:
            failures.append((s, missing))

        print(f"Ticker: {s:12s} | Company: {str(company):32s} | Sector: {str(sector):20s} | Status: {status}")
        print(f"  MCap: {str(mcap):10s} | PE: {str(pe):6s} | EPS: {str(eps):6s} | Rev: {str(rev):10s} | PAT: {str(pat):10s}")
        print(f"  Shareholding -> Promoter: {str(promoter)}% | FII: {str(fii)}% | DII: {str(dii)}% | Public: {str(public)}%\n")

    print("================================================")
    if not failures:
        print(" ALL TICKERS PASSED VERIFICATION! NO N/A METRICS!")
        print("================================================")
        return 0
    else:
        print(f" {len(failures)} TICKERS HAD MISSING VALUES:")
        for sym, miss in failures:
            print(f"   - {sym}: {miss}")
        print("================================================")
        return 1

if __name__ == "__main__":
    exit(verify())
