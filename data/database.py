import sqlite3
import pandas as pd

DB = "stock_data.db"


def save_prices(df):
    with sqlite3.connect(DB) as conn:
        df.to_sql(
            "prices",
            conn,
            if_exists="append",
            index=False
        )


def save_fundamentals(df):
    with sqlite3.connect(DB) as conn:
        df.to_sql(
            "fundamentals",
            conn,
            if_exists="replace",
            index=False
        )


def load_prices(symbol):
    with sqlite3.connect(DB) as conn:
        return pd.read_sql_query(
            "SELECT * FROM prices WHERE Symbol=? ORDER BY Date",
            conn,
            params=(symbol,)
        )