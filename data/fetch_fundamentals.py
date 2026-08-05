import yfinance as yf


def _safe_div(numerator, denominator):
    try:
        if numerator is None or denominator is None or denominator == 0:
            return None
        return float(numerator) / float(denominator)
    except Exception:
        return None


def fetch_fundamentals(symbol):
    try:
        stock = yf.Ticker(symbol)
        info = stock.info

        total_assets = info.get("totalAssets")
        total_debt = info.get("totalDebt")
        net_income = info.get("netIncome")
        ebit = info.get("ebit")
        book_value = info.get("bookValue")
        shares_outstanding = info.get("sharesOutstanding")

        roe = info.get("returnOnEquity")
        roce = info.get("returnOnCapitalEmployed")
        roa = info.get("returnOnAssets")

        # Try to locate an explicit shareholders' equity value from common keys
        shareholders_equity = info.get("totalStockholderEquity") or info.get("totalStockholdersEquity") or info.get("stockholdersEquity")
        if shareholders_equity is None and book_value is not None and shares_outstanding is not None:
            # book value is usually per share; multiply to get equity
            try:
                shareholders_equity = float(book_value) * float(shares_outstanding)
            except Exception:
                shareholders_equity = None

        if roe is None and net_income is not None:
            if shareholders_equity is not None:
                roe = _safe_div(net_income, shareholders_equity)
            elif total_assets is not None and total_debt is not None:
                roe = _safe_div(net_income, total_assets - total_debt)

        if roce is None and ebit is not None:
            if total_assets is not None and total_debt is not None:
                roce = _safe_div(ebit, total_assets - total_debt)
            else:
                # fallback: try using (marketCap + totalDebt - cash)/capital_employed if available
                capital_employed = info.get("capitalEmployed") or (info.get("marketCap") and info.get("totalDebt") and (info.get("marketCap") + info.get("totalDebt")))
                if capital_employed:
                    roce = _safe_div(ebit, capital_employed)

        if roa is None and net_income is not None and total_assets is not None:
            roa = _safe_div(net_income, total_assets)

        return {
            "Symbol": symbol,
            "Company": info.get("longName"),
            "Sector": info.get("sector"),
            "Industry": info.get("industry"),
            "MarketCap": info.get("marketCap"),
            "PE": info.get("trailingPE"),
            "ForwardPE": info.get("forwardPE"),
            "PriceSales": info.get("priceToSalesTrailing12Months"),
            "ROE": roe,
            "ROCE": roce,
            "ROA": roa,
            "RevenueGrowth": info.get("revenueGrowth"),
            "EarningsGrowth": info.get("earningsGrowth"),
            "EarningsQuarterlyGrowth": info.get("earningsQuarterlyGrowth"),
            "DebtEquity": info.get("debtToEquity"),
            "ProfitMargin": info.get("profitMargins"),
            "DividendYield": info.get("dividendYield"),
            "NetIncome": net_income,
            "TotalAssets": total_assets,
            "TotalDebt": total_debt,
            "OperatingCashFlow": info.get("operatingCashflow"),
            "GrossMargins": info.get("grossMargins"),
            "EBIT": ebit,
            "CurrentRatio": info.get("currentRatio"),
            "QuickRatio": info.get("quickRatio"),
            "BookValue": info.get("bookValue"),
            "SharesOutstanding": shares_outstanding,
            "FloatShares": info.get("floatShares"),
            "InstitutionsPercentHeld": info.get("institutionsPercentHeld"),
            "InsidersPercentHeld": info.get("insidersPercentHeld"),
            "SharesShort": info.get("sharesShort"),
            "SharesShortPriorMonth": info.get("sharesShortPriorMonth"),
        }

    except Exception as e:
        print(f"Fundamental error {symbol}: {e}")
        return {}
