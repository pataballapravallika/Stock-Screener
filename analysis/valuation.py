from typing import Optional


def safe_float(v):
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def compute_peg(pe: Optional[float], eps_growth: Optional[float]) -> Optional[float]:
    """Compute PEG = PE / (EPS growth % in whole numbers), return None if invalid.

    EPS growth must be a decimal (e.g., 0.2 for 20%). Only compute when both inputs valid and growth > 0.
    """
    p = safe_float(pe)
    g = safe_float(eps_growth)
    if p is None or g is None:
        return None
    if g <= 0:
        return None
    # PEG typically uses PE divided by growth rate in percentage or decimal depending convention.
    # We'll use PE / (g*100) to express PEG in conventional terms (i.e., PE divided by %growth).
    try:
        return p / (g * 100.0)
    except Exception:
        return None


def compute_ev_ebitda(enterprise_value: Optional[float], ebitda: Optional[float]) -> Optional[float]:
    ev = safe_float(enterprise_value)
    eb = safe_float(ebitda)
    if ev is None or eb is None or eb == 0:
        return None
    return ev / eb
