from data.database import get_company_info
for t in ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'SBIN']:
    info = get_company_info(t)
    print(f'{t}: {info}')
