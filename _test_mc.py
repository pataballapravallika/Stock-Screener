from data.providers.nse_xbrl_provider import NSEXBRLProvider
provider = NSEXBRLProvider()
html = provider._nse_get_html('/get-quotes/equity/RELIANCE')
if html:
    import re
    # Search for marketCap pattern
    patterns = [
        r'"marketCap"\s*:\s*([0-9,]+)',
        r'marketCap.*?([0-9,]+)',
        r' Market Cap.*₹\s*([0-9,]+)',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            print(f'Pattern {pat[:30]}: {m.group(1)}')
    
    # Look for company name  
    m = re.search(r'"companyName"\s*:\s*"([^"]+)"', html)
    if m:
        print(f'Company name: {m.group(1)}')
    
    # Look for any numbers near "market" 
    import re as _re
    matches = _re.findall(r'(?:market|cap|value|₹|crore|Cap)[^0-9]*([0-9,]+)', html[:5000], _re.IGNORECASE)
    print('Market/cap matches:', matches[:5])
    
    # Print a snippet of the HTML around "market" or "cap"
    for m in _re.finditer(r'(?i)(market.{0,5}cap|cap.{0,5}ital|marketCap)', html):
        start = max(0, m.start() - 50)
        end = min(len(html), m.end() + 100)
        print(f'Context: ...{html[start:end]}...')
        break
else:
    print('No HTML returned')
