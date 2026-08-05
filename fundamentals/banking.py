import numpy as np
from typing import Optional, Dict, Any


def safe_float(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_banking_metrics(income_stmt: dict, balance_sheet: dict) -> dict:
    result = {}
    missing = []

    interest_income = safe_float(income_stmt.get("Interest_Income"))
    interest_expense = safe_float(income_stmt.get("Interest_Expense"))
    total_income = safe_float(income_stmt.get("Total_Income"))
    non_interest_income = safe_float(income_stmt.get("Non_Interest_Income"))
    net_interest_income = None

    if interest_income is not None and interest_expense is not None:
        net_interest_income = interest_income - interest_expense
        result["NII"] = net_interest_income

    if net_interest_income is not None and total_income is not None and total_income != 0:
        result["NIM"] = (net_interest_income / total_income) * 100

    if total_income is not None and total_income != 0:
        if non_interest_income is not None:
            result["CASA_Ratio"] = (non_interest_income / total_income) * 100
        else:
            result["CASA_Ratio"] = None
            missing.append("casa_ratio")

    gross_npa = safe_float(balance_sheet.get("Gross_NPA"))
    net_npa = safe_float(balance_sheet.get("Net_NPA"))
    total_advances = safe_float(balance_sheet.get("Total_Advances"))
    provisions = safe_float(balance_sheet.get("Provisions"))

    if gross_npa is not None and total_advances is not None and total_advances != 0:
        result["GNPA"] = (gross_npa / total_advances) * 100
    else:
        missing.append("gnpa")

    if net_npa is not None and total_advances is not None and total_advances != 0:
        result["NNPA"] = (net_npa / total_advances) * 100
    else:
        missing.append("nnpa")

    if gross_npa is not None and net_npa is not None and gross_npa != 0:
        result["PCR"] = ((gross_npa - net_npa) / gross_npa) * 100
    else:
        result["PCR"] = None
        missing.append("pcr")

    if total_advances is not None:
        result["Advances"] = total_advances

    total_deposits = safe_float(balance_sheet.get("Total_Deposits"))
    if total_deposits is not None:
        result["Deposits"] = total_deposits

    car = safe_float(balance_sheet.get("CAR"))
    if car is not None:
        result["CAR"] = car
    else:
        missing.append("car")

    roa = safe_float(income_stmt.get("ROA"))
    if roa is not None:
        result["ROA"] = roa
    else:
        missing.append("roa")

    roe = safe_float(income_stmt.get("ROE"))
    if roe is not None:
        result["ROE"] = roe
    else:
        missing.append("roe")

    result["missing"] = missing
    return result
