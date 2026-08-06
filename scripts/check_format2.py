import re

files = [
    r'D:\career-projects\Stock_Screener\pages\2_Growth_Analysis.py',
    r'D:\career-projects\Stock_Screener\pages\3_Quality_Analysis.py',
    r'D:\career-projects\Stock_Screener\pages\5_Technical_Analysis.py',
    r'D:\career-projects\Stock_Screener\pages\6_Valuation.py',
    r'D:\career-projects\Stock_Screener\pages\10_Sector_Rotation.py',
    r'D:\career-projects\Stock_Screener\pages\11_Ranking_Engine.py',
    r'D:\career-projects\Stock_Screener\pages\12_Alerts_AI.py',
]

for f in files:
    with open(f, 'r') as fh:
        content = fh.read()
    applies = re.findall(r'\.apply\(lambda[^)]+\)', content)
    problematic = []
    for a in applies:
        # Check if the lambda uses f-string formatting
        if 'f"' in a or "f'" in a:
            problematic.append(a[:100])
    if problematic:
        print(f'\n{f}:')
        for p in problematic:
            print(f'  {p}')