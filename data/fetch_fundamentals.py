import yfinance as yf


def fetch_fundamentals(symbol):
    try:
        stock = yf.Ticker(symbol)
        info = stock.info

        return {
            "Symbol": symbol,
            "Company": info.get("longName"),
            "Sector": info.get("sector"),
            "Industry": info.get("industry"),
            "MarketCap": info.get("marketCap"),
            "PE": info.get("trailingPE"),
            "ForwardPE": info.get("forwardPE"),
            "PriceSales": info.get("priceToSalesTrailing12Months"),
            "ROE": info.get("returnOnEquity"),
            "ROCE": info.get("returnOnCapitalEmployed"),
            "ROA": info.get("returnOnAssets"),
            "RevenueGrowth": info.get("revenueGrowth"),
            "EarningsGrowth": info.get("earningsGrowth"),
            "DebtEquity": info.get("debtToEquity"),
            "ProfitMargin": info.get("profitMargins"),
            "DividendYield": info.get("dividendYield"),
            "NetIncome": info.get("netIncome"),
            "TotalAssets": info.get("totalAssets"),
            "TotalDebt": info.get("totalDebt"),
            "OperatingCashFlow": info.get("operatingCashflow"),
            "GrossMargins": info.get("grossMargins"),
            "EBIT": info.get("ebit"),
            "CurrentRatio": info.get("currentRatio"),
            "QuickRatio": info.get("quickRatio"),
            "BookValue": info.get("bookValue"),
            "SharesOutstanding": info.get("sharesOutstanding"),
        }

    except Exception as e:
        print(f"Fundamental error {symbol}: {e}")
        return {}
