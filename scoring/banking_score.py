import pandas as pd
import numpy as np
from typing import Optional
from scoring.config import (
    ScoringConfig,
    DEFAULT_CONFIG,
    DEFAULT_BANKING_CONFIG,
)
from scoring.fundamental_score import safe_float

def score_banking(
    banking_fundamentals: dict,
    config: Optional[ScoringConfig] = None,
    bc: Optional[DEFAULT_BANKING_CONFIG] = None,
) -> dict:
    if config is None:
        config = DEFAULT_CONFIG
    if bc is None:
        from scoring.config import DEFAULT_BANKING_CONFIG
        bc = DEFAULT_BANKING_CONFIG

    score = 0
    max_score = 0
    details = {}
    unavailable = []

    nim = safe_float(banking_fundamentals.get("NIM"))
    nii = safe_float(banking_fundamentals.get("NII"))
    casa = safe_float(banking_fundamentals.get("CASA_Ratio"))
    gnpa = safe_float(banking_fundamentals.get("GNPA"))
    nnpa = safe_float(banking_fundamentals.get("NNPA"))
    pcr = safe_float(banking_fundamentals.get("PCR"))
    advances_growth = safe_float(banking_fundamentals.get("Advances_Growth"))
    deposits_growth = safe_float(banking_fundamentals.get("Deposits_Growth"))
    car = safe_float(banking_fundamentals.get("CAR"))
    roa = safe_float(banking_fundamentals.get("ROA"))
    roe = safe_float(banking_fundamentals.get("ROE"))

    if nim is not None:
        max_score += bc.nim_weight
        if nim > 3.0:
            score += bc.nim_weight
            details["nim_pass"] = True
        else:
            details["nim_pass"] = False
    else:
        unavailable.append("nim")

    if nii is not None:
        max_score += bc.nii_weight
        if nii > 0:
            score += bc.nii_weight
            details["nii_pass"] = True
        else:
            details["nii_pass"] = False
    else:
        unavailable.append("nii")

    if casa is not None:
        max_score += bc.casa_weight
        if casa > 40:
            score += bc.casa_weight
            details["casa_pass"] = True
        else:
            details["casa_pass"] = False
    else:
        unavailable.append("casa")

    if gnpa is not None:
        max_score += bc.gnpa_weight
        if gnpa < 5:
            score += bc.gnpa_weight
            details["gnpa_pass"] = True
        else:
            details["gnpa_pass"] = False
    else:
        unavailable.append("gnpa")

    if nnpa is not None:
        max_score += bc.nnpa_weight
        if nnpa < 3:
            score += bc.nnpa_weight
            details["nnpa_pass"] = True
        else:
            details["nnpa_pass"] = False
    else:
        unavailable.append("nnpa")

    if pcr is not None:
        max_score += bc.pcr_weight
        if pcr > 60:
            score += bc.pcr_weight
            details["pcr_pass"] = True
        else:
            details["pcr_pass"] = False
    else:
        unavailable.append("pcr")

    if advances_growth is not None:
        max_score += bc.advances_growth_weight
        if advances_growth > 0:
            score += bc.advances_growth_weight
            details["advances_growth_pass"] = True
        else:
            details["advances_growth_pass"] = False
    else:
        unavailable.append("advances_growth")

    if deposits_growth is not None:
        max_score += bc.deposits_growth_weight
        if deposits_growth > 0:
            score += bc.deposits_growth_weight
            details["deposits_growth_pass"] = True
        else:
            details["deposits_growth_pass"] = False
    else:
        unavailable.append("deposits_growth")

    if car is not None:
        max_score += bc.car_weight
        if car > 15:
            score += bc.car_weight
            details["car_pass"] = True
        else:
            details["car_pass"] = False
    else:
        unavailable.append("car")

    if roa is not None:
        max_score += bc.roa_weight
        if roa > 1.0:
            score += bc.roa_weight
            details["roa_pass"] = True
        else:
            details["roa_pass"] = False
    else:
        unavailable.append("roa")

    if roe is not None:
        max_score += bc.roe_weight
        if roe > 15:
            score += bc.roe_weight
            details["roe_pass"] = True
        else:
            details["roe_pass"] = False
    else:
        unavailable.append("roe")

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
