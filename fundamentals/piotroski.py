import numpy as np
from typing import Optional, Dict, Any, List
from fundamentals.ratios import compute_roe, compute_roa, compute_opm, compute_debt_equity


def safe_float(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_piotroski_f_score(
    current_income: dict,
    previous_income: dict,
    current_balance: dict,
    previous_balance: dict,
    current_cashflow: dict,
) -> Dict[str, Any]:
    signals = {}
    score = 0
    missing = []

    roa_now = compute_roe(
        current_income.get("Net_Income"),
        current_balance.get("Total_Assets")
    )
    roa_prev = compute_roe(
        previous_income.get("Net_Income"),
        previous_balance.get("Total_Assets")
    )

    if roa_now is not None:
        if roa_now > 0:
            score += 1
            signals["positive_roa"] = True
        else:
            signals["positive_roa"] = False
    else:
        missing.append("positive_roa")

    ocf_now = safe_float(current_cashflow.get("Operating_Cash_Flow"))
    if ocf_now is not None:
        if ocf_now > 0:
            score += 1
            signals["positive_cfo"] = True
        else:
            signals["positive_cfo"] = False
    else:
        missing.append("positive_cfo")

    if roa_now is not None and roa_prev is not None:
        if roa_now > roa_prev:
            score += 1
            signals["improved_roa"] = True
        else:
            signals["improved_roa"] = False
    else:
        missing.append("improved_roa")

    ni_now = safe_float(current_income.get("Net_Income"))
    ni_prev = safe_float(previous_income.get("Net_Income"))
    if ocf_now is not None and ni_now is not None:
        if ocf_now > ni_now:
            score += 1
            signals["cfo_gt_net_income"] = True
        else:
            signals["cfo_gt_net_income"] = False
    else:
        missing.append("cfo_gt_net_income")

    leverage_now = compute_debt_equity(
        current_balance.get("Total_Debt"),
        current_balance.get("Stockholders_Equity")
    )
    leverage_prev = compute_debt_equity(
        previous_balance.get("Total_Debt"),
        previous_balance.get("Stockholders_Equity")
    )

    if leverage_now is not None and leverage_prev is not None:
        if leverage_now < leverage_prev:
            score += 1
            signals["lower_leverage"] = True
        else:
            signals["lower_leverage"] = False
    else:
        missing.append("lower_leverage")

    current_ratio_now = None
    current_ratio_prev = None
    ca_now = current_balance.get("Current_Assets")
    cl_now = current_balance.get("Current_Liabilities")
    ca_prev = previous_balance.get("Current_Assets")
    cl_prev = previous_balance.get("Current_Liabilities")

    if ca_now is not None and cl_now is not None and cl_now != 0:
        current_ratio_now = ca_now / cl_now
    if ca_prev is not None and cl_prev is not None and cl_prev != 0:
        current_ratio_prev = ca_prev / cl_prev

    if current_ratio_now is not None and current_ratio_prev is not None:
        if current_ratio_now > current_ratio_prev:
            score += 1
            signals["improved_current_ratio"] = True
        else:
            signals["improved_current_ratio"] = False
    else:
        missing.append("improved_current_ratio")

    shares_now = current_balance.get("Common_Shares_Outstanding")
    shares_prev = previous_balance.get("Common_Shares_Outstanding")
    if shares_now is not None and shares_prev is not None:
        if shares_now <= shares_prev:
            score += 1
            signals["no_dilution"] = True
        else:
            signals["no_dilution"] = False
    else:
        missing.append("no_dilution")

    gross_margin_now = None
    gross_margin_prev = None
    rev_now = safe_float(current_income.get("Revenue"))
    cogs_now = safe_float(current_income.get("COGS"))
    rev_prev = safe_float(previous_income.get("Revenue"))
    cogs_prev = safe_float(previous_income.get("COGS"))

    if rev_now is not None and cogs_now is not None and rev_now != 0:
        gross_margin_now = (rev_now - cogs_now) / rev_now
    if rev_prev is not None and cogs_prev is not None and rev_prev != 0:
        gross_margin_prev = (rev_prev - cogs_prev) / rev_prev

    if gross_margin_now is not None and gross_margin_prev is not None:
        if gross_margin_now > gross_margin_prev:
            score += 1
            signals["improved_gross_margin"] = True
        else:
            signals["improved_gross_margin"] = False
    else:
        missing.append("improved_gross_margin")

    asset_turnover_now = None
    asset_turnover_prev = None
    ta_now = safe_float(current_balance.get("Total_Assets"))
    ta_prev = safe_float(previous_balance.get("Total_Assets"))

    if rev_now is not None and ta_now is not None and ta_now != 0:
        asset_turnover_now = rev_now / ta_now
    if rev_prev is not None and ta_prev is not None and ta_prev != 0:
        asset_turnover_prev = rev_prev / ta_prev

    if asset_turnover_now is not None and asset_turnover_prev is not None:
        if asset_turnover_now > asset_turnover_prev:
            score += 1
            signals["improved_asset_turnover"] = True
        else:
            signals["improved_asset_turnover"] = False
    else:
        missing.append("improved_asset_turnover")

    return {
        "score": score,
        "max_score": 9,
        "signals": signals,
        "missing": missing,
        "available": len(missing) < 9,
    }
