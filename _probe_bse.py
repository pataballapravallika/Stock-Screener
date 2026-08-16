from playwright.sync_api import sync_playwright
import re, json

# BSE scrip codes for target companies
bse_codes = {
    'RELIANCE': 500010,
    'TCS': 532541,
    'INFY': 532273,
    'HDFCBANK': 532179,
    'SBIN': 532152,
}

tests = []
for ticker, code in bse_codes.items():
    tests.append((f'BSE_ANNALS_{ticker}', f'https://www.bseindia.com/annals/annals.aspx?anncid={code}'))
    tests.append((f'BSE_COMPANY_{ticker}', f'https://www.bseindia.com/StockReports/stock_report.aspx?code={code}'))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for name, url in tests[:4]:
        page = browser.new_page()
        page.set_default_timeout(20000)
        try:
            page.goto(url, timeout=20000, wait_until='domcontentloaded')
            content = page.content()
            title = page.title()
            pdfs = re.findall(r'href=["\']([^"\']*\.pdf[^"\']*)["\']', content, re.I)
            json_scripts = re.findall(r'<script[^>]*>(.*?)</script>', content, re.I | re.DOTALL)
            print(f"{name}: {url}")
            print(f"  title={title!r} len={len(content)} pdfs={len(pdfs)}")
            if pdfs:
                for pdf in pdfs[:3]:
                    print(f"  PDF: {pdf[:100]}")
            browser.close()
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            print(f"{name}: {url} -> ERROR: {e}")
    browser.close()
