import re
from typing import Any, Dict, List, Optional


class PDFParser:
    """Extract financial data from PDF reports.

    Uses pdfplumber when available; falls back to a simple regex-based
    line scanner for text-only PDFs.

    Never fabricates values; returns None for fields that cannot be
    reliably located.
    """

    LABEL_PATTERNS = {
        "revenue": re.compile(
            r"(?:Total\s+)?Revenue\b.*?([\d,]+\.?\d*)",
            re.IGNORECASE | re.DOTALL,
        ),
        "operating_profit": re.compile(
            r"Operating\s+Profit\b.*?([\d,]+\.?\d*)",
            re.IGNORECASE | re.DOTALL,
        ),
        "ebit": re.compile(
            r"(?:EBIT|Earnings\s+Before\s+Interest.*?Tax)\b.*?([\d,]+\.?\d*)",
            re.IGNORECASE | re.DOTALL,
        ),
        "pat": re.compile(
            r"(?:Net\s+Profit|PAT|Profit\s+After\s+Tax)\b.*?([\d,]+\.?\d*)",
            re.IGNORECASE | re.DOTALL,
        ),
        "eps": re.compile(
            r"(?:Earnings\s+Per\s+Share|EPS)\b.*?([\d,]+\.?\d*)",
            re.IGNORECASE | re.DOTALL,
        ),
        "total_assets": re.compile(
            r"Total\s+Assets\b.*?([\d,]+\.?\d*)",
            re.IGNORECASE | re.DOTALL,
        ),
        "current_assets": re.compile(
            r"Current\s+Assets\b.*?([\d,]+\.?\d*)",
            re.IGNORECASE | re.DOTALL,
        ),
        "total_liabilities": re.compile(
            r"Total\s+Liabilities\b.*?([\d,]+\.?\d*)",
            re.IGNORECASE | re.DOTALL,
        ),
        "current_liabilities": re.compile(
            r"Current\s+Liabilities\b.*?([\d,]+\.?\d*)",
            re.IGNORECASE | re.DOTALL,
        ),
        "equity": re.compile(
            r"(?:Shareholders['']?\s+Equity|Stockholders['']?\s+Equity|Total\s+Equity)\b.*?([\d,]+\.?\d*)",
            re.IGNORECASE | re.DOTALL,
        ),
        "total_debt": re.compile(
            r"(?:Total\s+Debt|Total\s+Borrowings)\b.*?([\d,]+\.?\d*)",
            re.IGNORECASE | re.DOTALL,
        ),
        "operating_cash_flow": re.compile(
            r"(?:Net\s+Cash\s+from\s+Operating|Cash\s+Flow\s+from\s+Operating)\b.*?([\d,]+\.?\d*)",
            re.IGNORECASE | re.DOTALL,
        ),
        "capex": re.compile(
            r"(?:Capital\s+Expenditure|CapEx|Purchase\s+of\s+(?:Fixed|Property))\b.*?([\d,]+\.?\d*)",
            re.IGNORECASE | re.DOTALL,
        ),
    }

    @classmethod
    def parse_file(cls, path: str) -> Dict[str, Any]:
        text = cls._extract_text(path)
        if not text:
            return {}
        return cls._extract_from_text(text)

    @classmethod
    def parse_bytes(cls, data: bytes, filename: str = "report.pdf") -> Dict[str, Any]:
        import tempfile, os
        suffix = os.path.splitext(filename)[1] or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            return cls.parse_file(tmp_path)
        finally:
            os.unlink(tmp_path)

    @classmethod
    def _extract_text(cls, path: str) -> str:
        text = ""
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            return text
        except Exception:
            pass

        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(path)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text
        except Exception:
            pass

        return ""

    @classmethod
    def _extract_from_text(cls, text: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for field, pattern in cls.LABEL_PATTERNS.items():
            match = pattern.search(text)
            if match:
                raw = match.group(1).replace(",", "").strip()
                try:
                    result[field] = float(raw)
                except ValueError:
                    result[field] = None
            else:
                result[field] = None
        return result
