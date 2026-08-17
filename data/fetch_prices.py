import yfinance as yf
import pandas as pd


PRICE_TICKER_FALLBACKS = {
    "TATAMOTORS.NS": ["TMPV.NS", "TATAMOTORS.BO"],
    "TATAMOTORS": ["TMPV.NS", "TATAMOTORS.BO"],
}

def fetch_prices(symbol, period="max"):
    # yfinance requires exchange suffixes (.NS for NSE, .BO for BSE)
    # for Indian stocks. Append .NS if the symbol lacks any suffix.
    clean = symbol.strip().upper()
    if not (clean.endswith(".NS") or clean.endswith(".BO") or clean.startswith("^")
            or clean.startswith(".") or any(c in clean for c in ["-", "_"])):
        clean = f"{clean}.NS"

    symbols_to_try = [clean]
    if clean in PRICE_TICKER_FALLBACKS:
        symbols_to_try.extend(PRICE_TICKER_FALLBACKS[clean])

    df = pd.DataFrame()
    for try_sym in symbols_to_try:
        try:
            df = yf.download(
                try_sym,
                period=period,
                interval="1d",
                auto_adjust=False,
                actions=False,
                progress=False
            )
            if not df.empty:
                break
        except Exception:
            continue

    if df.empty:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index()
    df["Symbol"] = symbol

    # Drop rows where Close is NaN (incomplete current-day data)
    if "Close" in df.columns:
        df = df.dropna(subset=["Close"])
        df = df.reset_index(drop=True)

    return df