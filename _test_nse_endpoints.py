from data.providers.nse_xbrl_provider import NSEXBRLProvider
provider = NSEXBRLProvider()
for endpoint in ['/quote-equity?symbol=RELIANCE', '/equity-detail?symbol=RELIANCE', '/companies-companyid?companyId=RELIANCE']:
    info = provider._nse_get(endpoint)
    print(endpoint + ':', 'OK' if info else 'None', '-', str(info)[:200] if info else '')
