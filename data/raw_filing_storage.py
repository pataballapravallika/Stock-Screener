"""Raw filing storage and metadata management.

Provides a persistent on-disk cache for official NSE XBRL filings
(plus official company investor-relations reports) so that the
Streamlit UI never depends on a live NSE request and never silently
falls back to third-party data sources.

Directory layout::

    data/raw_filings/<TICKER>/<YYYY-MM-DD>/
        filing.xml          – raw XBRL XML (or .pdf, .html)
        metadata.json       – source URL, period, company, checksum, etc.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from data.database import save_raw_filing, get_raw_filing

RAW_FILINGS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "raw_filings",
)


def _ticker_dir(ticker: str) -> str:
    return os.path.join(RAW_FILINGS_DIR, ticker.upper())


def _filing_dir(ticker: str, report_date: str) -> str:
    return os.path.join(_ticker_dir(ticker), report_date)


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def store_raw_filing(
    ticker: str,
    company: str,
    report_date: str,
    period: str,
    quarter: Optional[int],
    financial_year: Optional[int],
    consolidated: bool,
    source_url: str,
    source_type: str,
    content: bytes,
    filename: str = "filing.xml",
) -> str:
    """Save raw filing content to disk and record metadata in SQLite.

    Returns the file path of the stored filing.
    """
    fdir = _filing_dir(ticker, report_date)
    os.makedirs(fdir, exist_ok=True)
    fpath = os.path.join(fdir, filename)

    with open(fpath, "wb") as f:
        f.write(content)

    fhash = _file_hash(fpath)
    now = datetime.now(timezone.utc).isoformat()

    save_raw_filing({
        "ticker": ticker.upper(),
        "company": company,
        "report_date": report_date,
        "period": period,
        "quarter": quarter,
        "financial_year": financial_year,
        "consolidated": 1 if consolidated else 0,
        "source_url": source_url,
        "source_type": source_type,
        "file_path": fpath,
        "file_hash": fhash,
        "downloaded_at": now,
        "verification_status": "verified",
    })

    meta = {
        "ticker": ticker.upper(),
        "company": company,
        "report_date": report_date,
        "period": period,
        "quarter": quarter,
        "financial_year": financial_year,
        "consolidated": consolidated,
        "source_url": source_url,
        "source_type": source_type,
        "file_path": fpath,
        "file_hash": fhash,
        "downloaded_at": now,
        "verification_status": "verified",
    }
    meta_path = os.path.join(fdir, "metadata.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    return fpath


def load_raw_filing(ticker: str, report_date: str, period: str = None) -> Optional[Dict[str, Any]]:
    """Load a previously stored raw filing's metadata (and content path).

    Returns ``None`` if no verified filing exists for the given ticker
    and report date.
    """
    meta = get_raw_filing(ticker, report_date, period)
    if not meta or not meta.get("file_path"):
        return None
    return meta


def clear_raw_filing(ticker: str, report_date: str) -> None:
    """Remove a stored raw filing from disk and DB."""
    meta = get_raw_filing(ticker, report_date)
    if meta and meta.get("file_path"):
        fdir = _filing_dir(ticker, report_date)
        if os.path.isdir(fdir):
            shutil.rmtree(fdir, ignore_errors=True)


def ensure_raw_filings_dir() -> str:
    """Create the root raw-filings directory if it does not exist."""
    os.makedirs(RAW_FILINGS_DIR, exist_ok=True)
    return RAW_FILINGS_DIR
