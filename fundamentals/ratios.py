import pandas as pd
import numpy as np


def safe_float(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_roe(net_income, shareholders_equity):
    ni = safe_float(net_income)
    eq = safe_float(shareholders_equity)
    if ni is None or eq is None or eq == 0:
        return None
    return ni / eq


def compute_roa(net_income, total_assets):
    ni = safe_float(net_income)
    ta = safe_float(total_assets)
    if ni is None or ta is None or ta == 0:
        return None
    return ni / ta


def compute_roce(ebit, capital_employed):
    e = safe_float(ebit)
    ce = safe_float(capital_employed)
    if e is None or ce is None or ce == 0:
        return None
    return e / ce


def compute_debt_equity(total_debt, shareholders_equity):
    td = safe_float(total_debt)
    eq = safe_float(shareholders_equity)
    if td is None or eq is None or eq == 0:
        return None
    return td / eq


def compute_opm(operating_income, revenue):
    oi = safe_float(operating_income)
    rev = safe_float(revenue)
    if oi is None or rev is None or rev == 0:
        return None
    return oi / rev


def compute_npm(net_income, revenue):
    ni = safe_float(net_income)
    rev = safe_float(revenue)
    if ni is None or rev is None or rev == 0:
        return None
    return ni / rev


def compute_eps(net_income, shares_outstanding):
    ni = safe_float(net_income)
    so = safe_float(shares_outstanding)
    if ni is None or so is None or so == 0:
        return None
    return ni / so


def qoq_growth(current, previous):
    c = safe_float(current)
    p = safe_float(previous)
    if c is None or p is None or p == 0:
        return None
    return (c - p) / abs(p)


def yoy_growth(current, previous_year_same_quarter):
    c = safe_float(current)
    p = safe_float(previous_year_same_quarter)
    if c is None or p is None or p == 0:
        return None
    return (c - p) / abs(p)
