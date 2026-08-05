import pandas as pd
import numpy as np
from scoring.config import (
    ScoringConfig,
    FundamentalConfig,
    FundamentalThresholds,
    DEFAULT_CONFIG,
    DEFAULT_FUNDAMENTAL_CONFIG,
    DEFAULT_FUNDAMENTAL_THRESHOLDS,
)


def safe_float(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def score_fundamental(
    fundamentals: dict,
    config: Optional[ScoringConfig] = None,
    fc: Optional[FundamentalConfig] = None,
    thresholds: Optional[FundamentalThresholds] = None,
) -> dict:
    if config is None:
        config = DEFAULT_CONFIG
    if fc is None:
        fc = DEFAULT_FUNDAMENTAL_CONFIG
    if thresholds is None:
        thresholds = DEFAULT_FUNDAMENTAL_THRESHOLDS

    score = 0
    max_score = 0
    details = {}
    unavailable = []

    eps_growth = safe_float(fundamentals.get("EPS_Growth"))
    revenue_growth = safe_float(fundamentals.get("Revenue_Growth"))
    pat_growth = safe_float(fundamentals.get("PAT_Growth"))
    roe = safe_float(fundamentals.get("ROE"))
    roce = safe_float(fundamentals.get("ROCE"))
    roa = safe_float(fundamentals.get("ROA"))
    debt_equity = safe_float(fundamentals.get("Debt_Equity"))
    piotroski = fundamentals.get("Piotroski_FScore")
    altman = fundamentals.get("Altman_ZScore")

    if eps_growth is not None:
        max_score += fc.eps_growth_weight
        if eps_growth >= thresholds.eps_growth_min:
            score += fc.eps_growth_weight
            details["eps_growth_pass"] = True
        else:
            details["eps_growth_pass"] = False
    else:
        unavailable.append("eps_growth")

    if revenue_growth is not None:
        max_score += fc.revenue_growth_weight
        if revenue_growth >= thresholds.revenue_growth_min:
            score += fc.revenue_growth_weight
            details["revenue_growth_pass"] = True
        else:
            details["revenue_growth_pass"] = False
    else:
        unavailable.append("revenue_growth")

    if pat_growth is not None:
        max_score += fc.pat_growth_weight
        if pat_growth >= thresholds.pat_growth_min:
            score += fc.pat_growth_weight
            details["pat_growth_pass"] = True
        else:
            details["pat_growth_pass"] = False
    else:
        unavailable.append("pat_growth")

    if roe is not None:
        max_score += fc.roe_weight
        if roe >= thresholds.roe_min:
            score += fc.roe_weight
            details["roe_pass"] = True
        else:
            details["roe_pass"] = False
    else:
        unavailable.append("roe")

    if roce is not None:
        max_score += fc.roce_weight
        if roce >= thresholds.roce_min:
            score += fc.roce_weight
            details["roce_pass"] = True
        else:
            details["roce_pass"] = False
    else:
        unavailable.append("roce")

    if roa is not None:
        max_score += fc.roa_weight
        if roa >= thresholds.roa_min:
            score += fc.roa_weight
            details["roa_pass"] = True
        else:
            details["roa_pass"] = False
    else:
        unavailable.append("roa")

    if debt_equity is not None:
        max_score += fc.debt_equity_weight
        if debt_equity < thresholds.debt_equity_max:
            score += fc.debt_equity_weight
            details["debt_equity_pass"] = True
        else:
            details["debt_equity_pass"] = False
    else:
        unavailable.append("debt_equity")

    if piotroski is not None:
        max_score += fc.piotroski_weight
        if piotroski >= thresholds.piotroski_min:
            score += fc.piotroski_weight
            details["piotroski_pass"] = True
        else:
            details["piotroski_pass"] = False
    else:
        unavailable.append("piotroski")

    if altman is not None and isinstance(altman, dict) and altman.get("available"):
        max_score += fc.altman_weight
        if altman.get("value", 0) >= thresholds.altman_safe_threshold:
            score += fc.altman_weight
            details["altman_pass"] = True
        else:
            details["altman_pass"] = False
    else:
        unavailable.append("altman")

    percentage = (score / max_score * 100) if max_score > 0 else 0.0

    if percentage >= config.buy_threshold:
        signal = "BUY"
    elif percentage >= config.sell_threshold:
        signal = "HOLD"
    else:
        signal = "SELL"

    return {
        "score": score,
        "max_score": max_score,
        "percentage": round(percentage, 2),
        "signal": signal,
        "details": details,
        "unavailable": unavailable,
    }
