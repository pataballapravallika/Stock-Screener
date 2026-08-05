import numpy as np
from typing import Optional, Dict, Any


def safe_float(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_altman_z(
    working_capital,
    total_assets,
    retained_earnings,
    ebit,
    market_value_equity,
    total_liabilities,
    sales=None,
) -> Dict[str, Any]:
    wc = safe_float(working_capital)
    ta = safe_float(total_assets)
    re = safe_float(retained_earnings)
    ebit_val = safe_float(ebit)
    mve = safe_float(market_value_equity)
    tl = safe_float(total_liabilities)
    sales_val = safe_float(sales) if sales is not None else None

    if any(v is None for v in [wc, ta, re, ebit_val, mve, tl]) or ta == 0:
        return {"value": None, "status": "Unavailable", "available": False}

    x1 = wc / ta
    x2 = re / ta
    x3 = ebit_val / ta
    x4 = mve / tl
    x5 = sales_val / ta if sales_val is not None and ta != 0 else 0.0

    z = (
        1.2 * x1 +
        1.4 * x2 +
        3.3 * x3 +
        0.6 * x4 +
        1.0 * x5
    )

    if z >= 3.0:
        status = "Safe"
    elif z >= 1.8:
        status = "Grey"
    else:
        status = "Distress"

    return {
        "value": round(z, 2),
        "status": status,
        "available": True,
        "formula": "Altman Z-Score (original manufacturing formulation)",
    }
