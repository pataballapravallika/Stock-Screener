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
                promoter_pct REAL,
                fii_pct REAL,
                dii_pct REAL,
                govt_pct REAL,
                public_pct REAL,
                institutional_pct REAL,
                shareholders_count REAL,
                shareholding_json TEXT,
                shareholding_period TEXT,
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
                interest_income REAL,
                interest_expense REAL,
                total_income REAL,
                non_interest_income REAL,
                gross_npa REAL,
                net_npa REAL,
                total_advances REAL,
                provisions REAL,
                total_deposits REAL,
                car REAL,
                cash_and_cash_equivalents REAL,
                total_debt REAL,
                depreciation_amortization REAL,
                share_capital REAL,
                face_value REAL,
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
                cash_and_cash_equivalents REAL,
                total_debt REAL,
                depreciation_amortization REAL,
                share_capital REAL,
                face_value REAL,
                shares_outstanding REAL,
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

        # Add missing columns to existing tables
        company_cols = [
            ("promoter_pct", "REAL"), ("fii_pct", "REAL"), ("dii_pct", "REAL"),
            ("govt_pct", "REAL"), ("public_pct", "REAL"), ("institutional_pct", "REAL"),
            ("shareholders_count", "REAL"), ("shareholding_json", "TEXT"), ("shareholding_period", "TEXT")
        ]
        existing_comp_cols = {r[1] for r in conn.execute("PRAGMA table_info(companies)").fetchall()}
        for col_name, col_type in company_cols:
            if col_name not in existing_comp_cols:
                conn.execute(f"ALTER TABLE companies ADD COLUMN {col_name} {col_type}")

        for table, cols in [
            ("fundamental_reports", ["current_assets", "working_capital", "gross_profit", "cogs", "retained_earnings"]),
            ("fundamental_ttm", ["current_assets", "working_capital", "gross_profit", "retained_earnings"]),
        ]:
            existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for col in cols:
                if col not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} REAL")

        banking_cols = [
            ("interest_income", "REAL"), ("interest_expense", "REAL"),
            ("total_income", "REAL"), ("non_interest_income", "REAL"),
            ("gross_npa", "REAL"), ("net_npa", "REAL"),
            ("total_advances", "REAL"), ("provisions", "REAL"),
            ("total_deposits", "REAL"), ("car", "REAL"),
        ]
        for table in ["fundamental_reports", "fundamental_ttm"]:
            existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for col_name, col_type in banking_cols:
                if col_name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")

        valuation_cols = [
            ("cash_and_cash_equivalents", "REAL"),
            ("total_debt", "REAL"),
            ("depreciation_amortization", "REAL"),
            ("share_capital", "REAL"),
            ("face_value", "REAL"),
        ]
        for table in ["fundamental_reports", "fundamental_ttm"]:
            existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for col_name, col_type in valuation_cols:
                if col_name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")

        ttm_specific_cols = [
            ("shares_outstanding", "REAL"),
        ]
        for table in ["fundamental_ttm"]:
            existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for col_name, col_type in ttm_specific_cols:
                if col_name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")

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
    ticker = info.get("ticker") or info.get("symbol")
    if not ticker:
        return

    existing = get_company_info(ticker)
    company_name = info.get("company_name") or info.get("company") or existing.get("company_name")
    sector = info.get("sector") or existing.get("sector")
    industry = info.get("industry") or existing.get("industry")
    market_cap = info.get("market_cap") if info.get("market_cap") is not None else existing.get("market_cap")
    shares_outstanding = info.get("shares_outstanding") or info.get("sharesOutstanding") if (info.get("shares_outstanding") or info.get("sharesOutstanding")) is not None else existing.get("shares_outstanding")

    promoter_pct = info.get("promoter_pct") if info.get("promoter_pct") is not None else info.get("Promoter_Pct") if info.get("Promoter_Pct") is not None else existing.get("promoter_pct")
    fii_pct = info.get("fii_pct") if info.get("fii_pct") is not None else info.get("FII_Pct") if info.get("FII_Pct") is not None else existing.get("fii_pct")
    dii_pct = info.get("dii_pct") if info.get("dii_pct") is not None else info.get("DII_Pct") if info.get("DII_Pct") is not None else existing.get("dii_pct")
    govt_pct = info.get("govt_pct") if info.get("govt_pct") is not None else info.get("Govt_Pct") if info.get("Govt_Pct") is not None else existing.get("govt_pct")
    public_pct = info.get("public_pct") if info.get("public_pct") is not None else info.get("Public_Pct") if info.get("Public_Pct") is not None else existing.get("public_pct")
    institutional_pct = info.get("institutional_pct") if info.get("institutional_pct") is not None else info.get("Institutional_Pct") if info.get("Institutional_Pct") is not None else existing.get("institutional_pct")
    shareholders_count = info.get("shareholders_count") if info.get("shareholders_count") is not None else info.get("Shareholders_Count") if info.get("Shareholders_Count") is not None else existing.get("shareholders_count")
    shareholding_json = info.get("shareholding_json") or existing.get("shareholding_json")
    shareholding_period = info.get("shareholding_period") or info.get("Shareholding_Period") or existing.get("shareholding_period")

    with sqlite3.connect(DB) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO companies (
                ticker, company_name, sector, industry, market_cap, shares_outstanding,
                promoter_pct, fii_pct, dii_pct, govt_pct, public_pct, institutional_pct,
                shareholders_count, shareholding_json, shareholding_period, last_updated
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticker, company_name, sector, industry, market_cap, shares_outstanding,
            promoter_pct, fii_pct, dii_pct, govt_pct, public_pct, institutional_pct,
            shareholders_count, shareholding_json, shareholding_period, datetime.utcnow().isoformat(),
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
             gross_profit, cogs, retained_earnings,
             interest_income, interest_expense, total_income, non_interest_income,
             gross_npa, net_npa, total_advances, provisions, total_deposits, car,
             cash_and_cash_equivalents, total_debt, depreciation_amortization,
             share_capital, face_value,
             source, source_url, source_type, consolidated, unit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            record.get("interest_income"),
            record.get("interest_expense"),
            record.get("total_income"),
            record.get("non_interest_income"),
            record.get("gross_npa"),
            record.get("net_npa"),
            record.get("total_advances"),
            record.get("provisions"),
            record.get("total_deposits"),
            record.get("car"),
            record.get("cash_and_cash_equivalents"),
            record.get("total_debt"),
            record.get("depreciation_amortization"),
            record.get("share_capital"),
            record.get("face_value"),
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
        df = pd.read_sql_query(
            "SELECT * FROM fundamental_reports WHERE ticker=? AND period='quarterly' ORDER BY report_date DESC, financial_year DESC, quarter DESC",
            conn,
            params=(ticker,)
        )
    if df.empty:
        return df

    seen_periods = set()
    dedup_rows = []
    for _, row in df.iterrows():
        r_date = str(row.get("report_date") or "").strip()
        if not r_date:
            continue
        try:
            dt = pd.to_datetime(r_date)
            end_dt = dt + pd.offsets.MonthEnd(0)
            norm_date = end_dt.strftime("%Y-%m-%d")
            period_key = f"{dt.year}-{dt.month:02d}"
        except Exception:
            norm_date = r_date
            period_key = r_date

        if period_key not in seen_periods:
            seen_periods.add(period_key)
            row_dict = row.to_dict()
            row_dict["report_date"] = norm_date
            dedup_rows.append(row_dict)
            if len(dedup_rows) == count:
                break

    return pd.DataFrame(dedup_rows)


def repair_and_deduplicate_db():
    """Repair and deduplicate all fundamental_reports in database."""
    with sqlite3.connect(DB) as conn:
        df = pd.read_sql_query("SELECT * FROM fundamental_reports", conn)
    if df.empty:
        return

    records_by_key = {}
    for _, row in df.iterrows():
        r_dict = row.to_dict()
        ticker = r_dict.get("ticker")
        period = r_dict.get("period")
        r_date = str(r_dict.get("report_date") or "").strip()
        if not ticker or not r_date:
            continue

        try:
            dt = pd.to_datetime(r_date)
            end_dt = dt + pd.offsets.MonthEnd(0)
            norm_date = end_dt.strftime("%Y-%m-%d")
        except Exception:
            norm_date = r_date

        month = pd.to_datetime(norm_date).month if norm_date else 1
        if period == "quarterly":
            if 4 <= month <= 6:
                q = 1
            elif 7 <= month <= 9:
                q = 2
            elif 10 <= month <= 12:
                q = 3
            else:
                q = 4
            fy = (pd.to_datetime(norm_date).year + 1) if month >= 4 else pd.to_datetime(norm_date).year
        else:
            q = None
            fy = r_dict.get("financial_year") or (pd.to_datetime(norm_date).year if month < 4 else pd.to_datetime(norm_date).year + 1)

        r_dict["report_date"] = norm_date
        r_dict["quarter"] = q
        r_dict["financial_year"] = fy

        key = (ticker, norm_date, period)
        if key not in records_by_key:
            records_by_key[key] = r_dict
        else:
            existing = records_by_key[key]
            existing_non_nulls = sum(1 for v in existing.values() if pd.notna(v))
            new_non_nulls = sum(1 for v in r_dict.values() if pd.notna(v))
            if new_non_nulls > existing_non_nulls or r_dict.get("source") == "nse_xbrl":
                records_by_key[key] = r_dict

    with sqlite3.connect(DB) as conn:
        conn.execute("DELETE FROM fundamental_reports")
        conn.commit()

    for r in records_by_key.values():
        r.pop("id", None)
        save_fundamental_report(r)

    with sqlite3.connect(DB) as conn:
        tickers = [row[0] for row in conn.execute("SELECT DISTINCT ticker FROM fundamental_reports").fetchall()]

    from data.calculations.financial_calculator import FinancialCalculator
    calc = FinancialCalculator()
    for t in tickers:
        q_df = get_latest_quarterly_reports(t, limit=4)
        if not q_df.empty and len(q_df) >= 4:
            reports = q_df.to_dict("records")
            ttm = calc.compute_ttm(reports)
            if ttm:
                ttm["ticker"] = t
                ttm["period"] = "ttm"
                save_ttm_record(ttm)


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
             interest_income, interest_expense, total_income, non_interest_income,
             gross_npa, net_npa, total_advances, provisions, total_deposits, car,
             cash_and_cash_equivalents, total_debt, depreciation_amortization,
             share_capital, face_value, shares_outstanding,
             source, source_url, source_type, consolidated, unit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            record.get("interest_income"),
            record.get("interest_expense"),
            record.get("total_income"),
            record.get("non_interest_income"),
            record.get("gross_npa"),
            record.get("net_npa"),
            record.get("total_advances"),
            record.get("provisions"),
            record.get("total_deposits"),
            record.get("car"),
            record.get("cash_and_cash_equivalents"),
            record.get("total_debt"),
            record.get("depreciation_amortization"),
            record.get("share_capital"),
            record.get("face_value"),
            record.get("shares_outstanding"),
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
