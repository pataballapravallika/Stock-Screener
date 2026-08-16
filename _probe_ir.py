from playwright.sync_api import sync_playwright
import re, sys

candidates = [
  ('RELIANCE', 'https://www.relianceindustries.com/investor-relations/financial-results'),
  ('INFY', 'https://www.infosys.com/investors/financial-results/'),
  ('HDFCBANK', 'https://www.hdfcbank.com/investor-relations'),
  ('TCS', 'https://www.tcs.com/en/investors'),
  ('SBI', 'https://www.sbi.co.in/web/investor-relations'),
  ('BSE_HOME', 'https://www.bseindia.com/stock-reports/'),
]
for name, url in candidates:
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_default_timeout(25000)
            try:
                page.goto(url, timeout=25000, wait_until='domcontentloaded')
            except Exception as e:
                print(f"{name}: goto error {e}")
                browser.close()
                continue
            body = page.content()
            pdfs = re.findall(r'href=["\']([^"\']*\.pdf[^"\']*)["\']', body, re.I)
            title = page.title()
            print(f"{name}: {url}")
            print(f"  title={title!r} len={len(body)} pdfs={len(pdfs)}")
            for pdf in pdfs[:8]:
                print(f"    PDF: {pdf[:120]}")
            browser.close()
    except Exception as e:
        print(f"{name}: {url} -> ERROR: {e}")
