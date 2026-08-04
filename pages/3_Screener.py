import streamlit as st
import yfinance as yf
import pandas as pd


COMPANIES = {
    "Reliance": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "Infosys": "INFY.NS",
    "HDFC Bank": "HDFCBANK.NS",
    "ICICI Bank": "ICICIBANK.NS",
    "SBI": "SBIN.NS",
    "ITC": "ITC.NS",
    "Wipro": "WIPRO.NS",
    "HCL Tech": "HCLTECH.NS"
}


def analyse(symbol):

    df = yf.download(
        symbol,
        period="2y",
        progress=False,
        auto_adjust=False
    )

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if len(df) < 200:
        return None

    close = df["Close"]

    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()

    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1/14,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1/14,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss

    rsi = 100 - (
        100 /
        (1 + rs)
    )

    ema12 = close.ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = close.ewm(
        span=26,
        adjust=False
    ).mean()

    macd = ema12 - ema26

    signal = macd.ewm(
        span=9,
        adjust=False
    ).mean()

    high52 = (
        df["High"]
        .rolling(252)
        .max()
    )

    distance = (
        (close.iloc[-1] - high52.iloc[-1])
        /
        high52.iloc[-1]
    ) * 100

    score = 0

    if close.iloc[-1] > ma200.iloc[-1]:
        score += 25

    if ma50.iloc[-1] > ma200.iloc[-1]:
        score += 20

    if 50 <= rsi.iloc[-1] <= 70:
        score += 20

    if macd.iloc[-1] > signal.iloc[-1]:
        score += 20

    if distance >= -10:
        score += 15

    return {
        "Price": close.iloc[-1],
        "MA50": ma50.iloc[-1],
        "MA200": ma200.iloc[-1],
        "RSI": rsi.iloc[-1],
        "MACD": macd.iloc[-1],
        "52W Distance %": distance,
        "Technical Score": score
    }


st.title(" Stock Screener")

st.write(
    "Rank stocks using technical screening rules."
)


if st.button("Run Screener"):

    results = []

    progress = st.progress(0)

    total = len(COMPANIES)

    for index, (
        company,
        symbol
    ) in enumerate(
        COMPANIES.items()
    ):

        result = analyse(symbol)

        if result:

            result["Company"] = company
            result["Symbol"] = symbol

            results.append(result)

        progress.progress(
            (index + 1) / total
        )

    ranking = pd.DataFrame(results)

    ranking = ranking.sort_values(
        "Technical Score",
        ascending=False
    )

    ranking.insert(
        0,
        "Rank",
        range(
            1,
            len(ranking) + 1
        )
    )

    st.dataframe(
        ranking,
        use_container_width=True,
        hide_index=True
    )

    csv = ranking.to_csv(
        index=False
    )

    st.download_button(
        "Download Ranking",
        csv,
        "ranked_stocks.csv",
        "text/csv"
    )