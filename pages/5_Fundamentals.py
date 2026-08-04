import streamlit as st
import yfinance as yf
import pandas as pd


st.title(" Fundamental Analysis")


symbol = st.text_input(
    "Stock Symbol",
    "RELIANCE.NS"
)


if st.button(
    "Load Fundamentals"
):

    with st.spinner(
        "Fetching company fundamentals..."
    ):

        try:

            ticker = yf.Ticker(
                symbol
            )

            info = ticker.info


            fundamentals = {
                "Company":
                    info.get(
                        "longName"
                    ),

                "Sector":
                    info.get(
                        "sector"
                    ),

                "Industry":
                    info.get(
                        "industry"
                    ),

                "Market Cap":
                    info.get(
                        "marketCap"
                    ),

                "Trailing P/E":
                    info.get(
                        "trailingPE"
                    ),

                "Forward P/E":
                    info.get(
                        "forwardPE"
                    ),

                "Price / Sales":
                    info.get(
                        "priceToSalesTrailing12Months"
                    ),

                "ROE":
                    info.get(
                        "returnOnEquity"
                    ),

                "Revenue Growth":
                    info.get(
                        "revenueGrowth"
                    ),

                "Earnings Growth":
                    info.get(
                        "earningsGrowth"
                    ),

                "Debt / Equity":
                    info.get(
                        "debtToEquity"
                    ),

                "Profit Margin":
                    info.get(
                        "profitMargins"
                    ),

                "Dividend Yield":
                    info.get(
                        "dividendYield"
                    )
            }


            company = (
                fundamentals[
                    "Company"
                ]
                or symbol
            )


            st.subheader(
                company
            )


            c1, c2, c3, c4 = (
                st.columns(4)
            )


            market_cap = (
                fundamentals[
                    "Market Cap"
                ]
            )


            if market_cap:

                c1.metric(
                    "Market Cap",
                    f"₹{market_cap/1e9:,.2f}B"
                )

            else:

                c1.metric(
                    "Market Cap",
                    "N/A"
                )


            pe = fundamentals[
                "Trailing P/E"
            ]

            c2.metric(
                "P/E",
                (
                    f"{pe:.2f}"
                    if pe
                    else "N/A"
                )
            )


            roe = fundamentals[
                "ROE"
            ]

            c3.metric(
                "ROE",
                (
                    f"{roe*100:.2f}%"
                    if roe is not None
                    else "N/A"
                )
            )


            growth = fundamentals[
                "Revenue Growth"
            ]

            c4.metric(
                "Revenue Growth",
                (
                    f"{growth*100:.2f}%"
                    if growth is not None
                    else "N/A"
                )
            )


            # Table

            table = pd.DataFrame(
                fundamentals.items(),
                columns=[
                    "Metric",
                    "Value"
                ]
            )


            st.dataframe(
                table,
                use_container_width=True,
                hide_index=True
            )


        except Exception as e:

            st.error(
                f"Unable to retrieve "
                f"fundamentals: {e}"
            )