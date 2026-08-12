import pandas as pd
import numpy as np
from typing import Optional, Tuple, List

from data.database import get_latest_quarterly_reports


def get_quarterly_df(fund: dict) -> Optional[pd.DataFrame]:
    """Return provider quarterly_financials DataFrame if valid, else None."""
    if not fund or not isinstance(fund, dict):
        return None
    q = fund.get("quarterly_financials")
    if q is None:
        return None
    try:
        if isinstance(q, pd.DataFrame) and not q.empty:
            return q
    except Exception:
        return None
    return None


def find_eps_label(df: pd.DataFrame) -> Optional[str]:
    if df is None or df.empty:
        return None
    for label in ["Diluted EPS", "Basic EPS", "EPS"]:
        if label in df.index:
            return label
    return None


def quarterly_eps_series(fund: dict) -> List[Tuple[pd.Timestamp, Optional[float]]]:
    """Return list of (period_timestamp, eps) with most-recent-first order when possible.

    Always return empty list if EPS cannot be reliably identified.
    """
    df = get_quarterly_df(fund)
    if df is None:
        return []
    label = find_eps_label(df)
    if label is None:
        return []
    out = []
    for col in df.columns:
        # attempt to coerce to Timestamp
        try:
            ts = pd.to_datetime(col)
        except Exception:
            try:
                ts = pd.to_datetime(str(col))
            except Exception:
                ts = None
        val = df.loc[label, col]
        try:
            v = float(val) if not (pd.isna(val) or val is None) else None
        except Exception:
            v = None
        if ts is not None:
            out.append((ts, v))
    return out


def is_quarterly_periods(periods: List[pd.Timestamp]) -> bool:
    """Basic heuristic: check median difference ~90 days and at least 4 periods."""
    if not periods or len(periods) < 4:
        return False
    diffs = []
    for i in range(1, len(periods)):
        try:
            diffs.append(abs((periods[i-1] - periods[i]).days))
        except Exception:
            continue
    if not diffs:
        return False
    median = int(np.median(diffs))
    return 70 <= median <= 110
