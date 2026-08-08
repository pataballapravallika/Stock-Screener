import sqlite3
import pandas as pd
import os
from datetime import datetime

DB = "stock_data.db"


def init_db():
    with sqlite3.connect(DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                ticker TEXT PRIMARY KEY,
                company_name TEXT,
                sector TEXT,
                industry TEXT,
                market_cap REAL,
                shares_outstanding REAL,
                last_updated TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fundamental_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                company TEXT,
                report_date TEXT NOT NULL,
                period TEXT NOT NULL,
                quarter INTEGER,
                financial_year INTEGER NOT NULL,
                revenue REAL,
                operating_profit REAL,
                ebit REAL,
                pat REAL,
                eps REAL,
                equity REAL,
                assets REAL,
                liabilities REAL,
                current_assets REAL,
                current_liabilities REAL,
                working_capital REAL,
                debt REAL,
                operating_cash_flow REAL,
                capex REAL,
                gross_profit REAL,
                cogs REAL,
                retained_earnings REAL,
                source TEXT,
                source_url TEXT,
                source_type TEXT,
                consolidated INTEGER DEFAULT 1,
                unit TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticker, report_date, period)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fundamental_ttm (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                company TEXT,
                period TEXT NOT NULL,
                financial_year INTEGER NOT NULL,
                revenue REAL,
                operating_profit REAL,
                ebit REAL,
                pat REAL,
                eps REAL,
                equity REAL,
                assets REAL,
                liabilities REAL,
                current_assets REAL,
                current_liabilities REAL,
                working_capital REAL,
                debt REAL,
                operating_cash_flow REAL,
                capex REAL,
                gross_profit REAL,
                retained_earnings REAL,
                source TEXT,
                source_url TEXT,
                source_type TEXT,
                consolidated INTEGER DEFAULT 1,
                unit TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticker, period)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS validation_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                report_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        for table, cols in [
            ("fundamental_reports", ["current_assets", "working_capital", "gross_profit", "cogs", "retained_earnings"]),
            ("fundamental_ttm", ["current_assets", "working_capital", "gross_profit", "retained_earnings"]),
        ]:
            existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for col in cols:
                if col not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} REAL")

        for table, col_defs in [
            ("fundamental_reports", [("source_url", "TEXT"), ("source_type", "TEXT"), ("consolidated", "INTEGER"), ("unit", "TEXT")]),
            ("fundamental_ttm", [("source_url", "TEXT"), ("source_type", "TEXT"), ("consolidated", "INTEGER"), ("unit", "TEXT")]),
        ]:
            existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for col, col_type in col_defs:
                if col not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")

        conn.commit()


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


def save_company_info(info: dict = None, **kwargs):
    if info is None:
        info = kwargs
    elif kwargs:
        info = {**info, **kwargs}
    with sqlite3.connect(DB) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO companies (ticker, company_name, sector, industry, market_cap, shares_outstanding, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            info.get("ticker") or info.get("symbol"),
            info.get("company_name") or info.get("company"),
            info.get("sector"),
            info.get("industry"),
            info.get("market_cap"),
            info.get("shares_outstanding") or info.get("sharesOutstanding"),
            datetime.utcnow().isoformat(),
        ))
        conn.commit()


def get_company_info(ticker: str) -> dict:
    with sqlite3.connect(DB) as conn:
        row = conn.execute(
            "SELECT * FROM companies WHERE ticker=?", (ticker,)
        ).fetchone()
        if row is None:
            return {}
        cols = [d[1] for d in conn.execute("PRAGMA table_info(companies)").fetchall()]
        return dict(zip(cols, row))


def save_fundamental_report(record: dict = None, **kwargs):
    if record is None:
        record = kwargs
    elif kwargs:
        record = {**record, **kwargs}
    with sqlite3.connect(DB) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO fundamental_reports
            (ticker, company, report_date, period, quarter, financial_year,
             revenue, operating_profit, ebit, pat, eps,
             equity, assets, liabilities, current_assets, current_liabilities,
             working_capital, debt, operating_cash_flow, capex,
             gross_profit, cogs, retained_earnings, source,
             source_url, source_type, consolidated, unit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.get("ticker") or record.get("symbol"),
            record.get("company"),
            record.get("report_date"),
            record.get("period"),
            record.get("quarter"),
            record.get("financial_year"),
            record.get("revenue"),
            record.get("operating_profit"),
            record.get("ebit"),
            record.get("pat"),
            record.get("eps"),
            record.get("equity"),
            record.get("assets"),
            record.get("liabilities"),
            record.get("current_assets"),
            record.get("current_liabilities"),
            record.get("working_capital"),
            record.get("debt"),
            record.get("operating_cash_flow"),
            record.get("capex"),
            record.get("gross_profit"),
            record.get("cogs"),
            record.get("retained_earnings"),
            record.get("source"),
            record.get("source_url"),
            record.get("source_type"),
            record.get("consolidated"),
            record.get("unit"),
        ))
        conn.commit()


def get_fundamental_reports(ticker: str, period: str = None) -> pd.DataFrame:
    with sqlite3.connect(DB) as conn:
        query = "SELECT * FROM fundamental_reports WHERE ticker=?"
        params = [ticker]
        if period:
            query += " AND period=?"
            params.append(period)
        query += " ORDER BY financial_year DESC, quarter DESC"
        return pd.read_sql_query(query, conn, params=params)


def get_latest_quarterly_reports(ticker: str, n: int = 5, limit: int = None) -> pd.DataFrame:
    count = limit if limit is not None else n
    with sqlite3.connect(DB) as conn:
        return pd.read_sql_query(
            "SELECT * FROM fundamental_reports WHERE ticker=? AND period='quarterly' ORDER BY financial_year DESC, quarter DESC LIMIT ?",
            conn,
            params=(ticker, count)
        )


def get_latest_annual_reports(ticker: str, n: int = 5, limit: int = None) -> pd.DataFrame:
    count = limit if limit is not None else n
    with sqlite3.connect(DB) as conn:
        return pd.read_sql_query(
            "SELECT * FROM fundamental_reports WHERE ticker=? AND period='annual' ORDER BY financial_year DESC LIMIT ?",
            conn,
            params=(ticker, count)
        )


def save_ttm_record(record: dict = None, symbol: str = None, ttm_dict: dict = None, source: str = None):
    if record is None and ttm_dict is not None:
        record = dict(ttm_dict)
        if symbol:
            record["ticker"] = symbol
        if source:
            record["source"] = source
    if not record:
        return
    with sqlite3.connect(DB) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO fundamental_ttm
            (ticker, company, period, financial_year,
             revenue, operating_profit, ebit, pat, eps,
             equity, assets, liabilities, current_assets, current_liabilities,
             working_capital, debt, operating_cash_flow, capex,
             gross_profit, retained_earnings,
             source, source_url, source_type, consolidated, unit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.get("ticker") or record.get("symbol"),
            record.get("company"),
            record.get("period") or "ttm",
            record.get("financial_year") or datetime.now().year,
            record.get("revenue"),
            record.get("operating_profit"),
            record.get("ebit"),
            record.get("pat"),
            record.get("eps"),
            record.get("equity"),
            record.get("assets"),
            record.get("liabilities"),
            record.get("current_assets"),
            record.get("current_liabilities"),
            record.get("working_capital"),
            record.get("debt"),
            record.get("operating_cash_flow"),
            record.get("capex"),
            record.get("gross_profit"),
            record.get("retained_earnings"),
            record.get("source"),
            record.get("source_url"),
            record.get("source_type"),
            record.get("consolidated"),
            record.get("unit"),
        ))
        conn.commit()


def get_ttm_record(ticker: str, period: str = "ttm") -> dict:
    with sqlite3.connect(DB) as conn:
        row = conn.execute(
            "SELECT * FROM fundamental_ttm WHERE ticker=? AND period=?", (ticker, period)
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT * FROM fundamental_ttm WHERE ticker=? ORDER BY id DESC LIMIT 1", (ticker,)
            ).fetchone()
        if row is None:
            return {}
        cols = [d[1] for d in conn.execute("PRAGMA table_info(fundamental_ttm)").fetchall()]
        return dict(zip(cols, row))


def load_fundamentals(symbol: str) -> pd.DataFrame:
    with sqlite3.connect(DB) as conn:
        return pd.read_sql_query(
            "SELECT * FROM fundamental_reports WHERE ticker=? ORDER BY financial_year DESC, quarter DESC",
            conn,
            params=(symbol,)
        )


def save_validation_report(ticker: str, report_json: str):
    with sqlite3.connect(DB) as conn:
        conn.execute(
            "INSERT INTO validation_reports (ticker, report_json) VALUES (?, ?)",
            (ticker, report_json),
        )
        conn.commit()


def get_validation_reports(ticker: str) -> pd.DataFrame:
    with sqlite3.connect(DB) as conn:
        return pd.read_sql_query(
            "SELECT * FROM validation_reports WHERE ticker=? ORDER BY created_at DESC",
            conn,
            params=(ticker,),
        )
