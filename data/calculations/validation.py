import json
import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from data.calculations.financial_calculator import FinancialCalculator


VALIDATION_THRESHOLD = 0.05
REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
os.makedirs(REPORT_DIR, exist_ok=True)


# (extracted_field, canonical_label, numerator_for_ratio, denominator_for_ratio)
_FIELD_RATIO_PAIRS = [
    ("revenue",          "Revenue",             None,               None),
    ("operating_profit", "Operating Profit",    "operating_profit", "revenue"),
    ("ebit",             "EBIT",                 None,               None),
    ("pat",              "PAT",                  None,               None),
    ("eps",              "EPS",                  None,               None),
    ("assets",           "Total Assets",         None,               None),
    ("current_assets",   "Current Assets",       None,               None),
    ("liabilities",      "Total Liabilities",    None,               None),
    ("current_liabilities", "Current Liabilities", None,             None),
    ("equity",           "Shareholders' Equity", None,               None),
    ("debt",             "Total Debt",           None,               None),
    ("operating_cash_flow", "Operating Cash Flow", None,             None),
    ("capex",            "Capital Expenditure",  None,               None),
]

_RATIO_CHECKS = [
    ("roe",             "ROE",             "pat",  "equity"),
    ("roa",             "ROA",             "pat",  "assets"),
    ("roce",            "ROCE",            "ebit", None),  # special: needs assets - current_liabilities
    ("debt_equity",     "Debt/Equity",     "debt", "equity"),
    ("opm",             "OPM",             "operating_profit", "revenue"),
    ("npm",             "NPM",             "pat",  "revenue"),
]

_EXTRACTED_VS_CALCULATED = [
    ("roe",             "ROE",             lambda r: r.get("pat"),      lambda r: r.get("equity")),
    ("roa",             "ROA",             lambda r: r.get("pat"),      lambda r: r.get("assets")),
    ("debt_equity",     "Debt/Equity",     lambda r: r.get("debt"),     lambda r: r.get("equity")),
    ("opm",             "OPM",             lambda r: r.get("operating_profit"), lambda r: r.get("revenue")),
    ("npm",             "NPM",             lambda r: r.get("pat"),      lambda r: r.get("revenue")),
    ("roce",            "ROCE",            lambda r: r.get("ebit"),     lambda r: (r.get("assets"), r.get("current_liabilities"))),
]


class ValidationEngine:
    """Compares extracted values with internally calculated values.

    Produces a structured report highlighting differences above the
    5 % threshold.  Missing values on either side are flagged explicitly.
    """

    def __init__(self, threshold: float = VALIDATION_THRESHOLD):
        self.threshold = threshold

    def _pct_diff(self, extracted: Optional[float], calculated: Optional[float]) -> Optional[float]:
        if extracted is None and calculated is None:
            return None
        if extracted is None or calculated is None:
            return float("inf")
        e = FinancialCalculator._safe(extracted)
        c = FinancialCalculator._safe(calculated)
        if e is None or c is None:
            return float("inf")
        denom = max(abs(e), abs(c))
        if denom == 0:
            return 0.0
        return abs(e - c) / denom

    def _check_roce(self, record: Dict[str, Any]) -> tuple:
        ebit = FinancialCalculator._safe(record.get("ebit"))
        ta = FinancialCalculator._safe(record.get("assets"))
        cl = FinancialCalculator._safe(record.get("current_liabilities"))
        if ebit is None or ta is None or cl is None:
            return None, None
        capital_employed = ta - cl
        if capital_employed == 0:
            return None, None
        return ebit / capital_employed, ebit / capital_employed

    def validate_record(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        source_url = record.get("source_url") or ""
        source_type = record.get("source_type") or record.get("source") or "nse_xbrl"
        source_str = source_url if source_url else source_type

        for key, label, num_fn, den_fn in _EXTRACTED_VS_CALCULATED:
            if key == "roce":
                calc_val, direct_calc = self._check_roce(record)
            else:
                num = FinancialCalculator._safe(num_fn(record)) if callable(num_fn) else None
                den = FinancialCalculator._safe(den_fn(record)) if callable(den_fn) else None
                if num_fn and den_fn:
                    num = FinancialCalculator._safe(record.get(num_fn))
                    den = FinancialCalculator._safe(record.get(den_fn))
                calc_val = FinancialCalculator._div(num, den)
                direct_calc = calc_val

            extracted = record.get(key)
            diff = self._pct_diff(extracted, calc_val)
            status = "OK"
            if extracted is None and calc_val is None:
                status = "N/A"
                diff = None
            elif diff == float("inf"):
                status = "MISSING"
                diff = None
            elif diff is not None and diff > self.threshold:
                status = "MISMATCH"

            rep_str = f"{extracted:.4f}" if extracted is not None else "N/A"
            calc_str = f"{calc_val:.4f}" if calc_val is not None else "N/A"

            rows.append({
                "Metric": label,
                "Reported Value": rep_str,
                "Calculated Value": calc_str,
                "Source": source_str,
                "Status": status,
                "metric": label,
                "extracted": extracted,
                "calculated": calc_val,
                "diff_pct": diff * 100 if diff is not None else None,
                "status": status,
            })

        fcf_extracted = record.get("fcf")
        fcf_calculated = FinancialCalculator.compute_fcf(
            record.get("operating_cash_flow"), record.get("capex")
        )
        diff = self._pct_diff(fcf_extracted, fcf_calculated)
        status = "OK"
        if fcf_extracted is None and fcf_calculated is None:
            status = "N/A"
            diff = None
        elif diff == float("inf"):
            status = "MISSING"
            diff = None
        elif diff is not None and diff > self.threshold:
            status = "MISMATCH"

        rep_str = f"{fcf_extracted:.4f}" if fcf_extracted is not None else "N/A"
        calc_str = f"{fcf_calculated:.4f}" if fcf_calculated is not None else "N/A"

        rows.append({
            "Metric": "FreeCashFlow",
            "Reported Value": rep_str,
            "Calculated Value": calc_str,
            "Source": source_str,
            "Status": status,
            "metric": "FreeCashFlow",
            "extracted": fcf_extracted,
            "calculated": fcf_calculated,
            "diff_pct": diff * 100 if diff is not None else None,
            "status": status,
        })

        return rows

    def validate_company(self, symbol: str, records: Dict[str, Any]) -> Dict[str, Any]:
        quarterly = records.get("quarterly", [])
        annual = records.get("annual", [])
        ttm = records.get("ttm")

        result = {
            "symbol": symbol,
            "validated_at": datetime.now(timezone.utc).isoformat(),
            "threshold_pct": self.threshold * 100,
            "quarterly": [],
            "annual": [],
            "ttm": [],
            "summary": {
                "total_checks": 0,
                "mismatches": 0,
                "missing": 0,
                "ok": 0,
                "n/a": 0,
            },
        }

        for rec in quarterly:
            rows = self.validate_record(rec)
            result["quarterly"].append({
                "period": rec.get("report_date"),
                "financial_year": rec.get("financial_year"),
                "quarter": rec.get("quarter"),
                "rows": rows,
            })
            self._update_summary(result["summary"], rows)

        for rec in annual:
            rows = self.validate_record(rec)
            result["annual"].append({
                "period": rec.get("report_date"),
                "financial_year": rec.get("financial_year"),
                "quarter": rec.get("quarter"),
                "rows": rows,
            })
            self._update_summary(result["summary"], rows)

        if ttm:
            rows = self.validate_record(ttm)
            result["ttm"].append({
                "period": "TTM",
                "rows": rows,
            })
            self._update_summary(result["summary"], rows)

        return result

    def _update_summary(self, summary: Dict[str, int], rows: List[Dict[str, Any]]):
        for row in rows:
            summary["total_checks"] += 1
            key = str(row.get("status", "N/A")).lower()
            summary[key] = summary.get(key, 0) + 1

    def save_report(self, report: Dict[str, Any]) -> str:
        filename = f"validation_{report.get('symbol', 'unknown')}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        path = os.path.join(REPORT_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        return path

    def print_summary(self, report: Dict[str, Any]):
        s = report["summary"]
        print(f"\nValidation Summary for {report['symbol']}")
        print(f"  Threshold:  {s.get('threshold_pct', self.threshold * 100):.1f}%")
        print(f"  Total checks:  {s['total_checks']}")
        print(f"  OK:            {s['ok']}")
        print(f"  Mismatches:    {s['mismatches']}")
        print(f"  Missing:       {s['missing']}")

        for section in ["quarterly", "annual", "ttm"]:
            for period in report.get(section, []):
                label = period.get("period") or period.get("financial_year", "TTM")
                for row in period.get("rows", []):
                    if row["status"] != "OK":
                        diff_str = f"{row['diff_pct']:.2f}%" if row["diff_pct"] is not None else "N/A"
                        print(
                            f"  [{section} {label}] {row['metric']}: "
                            f"extracted={row['extracted']}, calculated={row['calculated']}, "
                            f"diff={diff_str}, status={row['status']}"
                        )

    def missing_fields_report(self, record: Dict[str, Any]) -> List[str]:
        required = [
            "revenue", "operating_profit", "ebit", "pat", "eps",
            "total_assets", "current_assets", "total_liabilities",
            "current_liabilities", "shareholders_equity", "total_debt",
            "operating_cash_flow", "capital_expenditure",
        ]
        missing = []
        for field in required:
            v = record.get(field)
            if v is None:
                missing.append(field)
        return missing
