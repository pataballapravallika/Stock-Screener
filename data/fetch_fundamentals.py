import yfinance as yf


def fetch_fundamentals(symbol):
    try:
        stock = yf.Ticker(symbol)
        info = stock.info

        return {
            "Symbol": symbol,
            "Company": info.get("longName"),
            "Sector": info.get("sector"),
            "MarketCap": info.get("marketCap"),
            "PE": info.get("trailingPE"),
            "ForwardPE": info.get("forwardPE"),
            "PriceSales": info.get("priceToSalesTrailing12Months"),
            "ROE": info.get("returnOnEquity"),
            "RevenueGrowth": info.get("revenueGrowth"),
            "EarningsGrowth": info.get("earningsGrowth"),
            "DebtEquity": info.get("debtToEquity")
        }

    except Exception as e:
        print(f"Fundamental error {symbol}: {e}")
        return {}