from typing import Any, Dict, Optional


XBRL_TAGS = {
    "revenue": [
        "RevenueFromOperations",
        "Income",
        "ifrs-full:Revenue",
        "ifrs-full:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:Revenues",
        "us-gaap:SalesRevenueNet",
        "acfr:Turnover",
    ],
    "operating_profit": [
        "ProfitBeforeExceptionalItemsAndTax",
        "ProfitLossFromOrdinaryActivitiesBeforeTax",
        "ProfitBeforeTax",
        "OperatingProfitBeforeProvisionAndContingencies",
        "ifrs-full:OperatingProfitLoss",
        "us-gaap:OperatingIncomeLoss",
    ],
    "ebit": [
        "ProfitBeforeExceptionalItemsAndTax",
        "ProfitLossFromOrdinaryActivitiesBeforeTax",
        "ProfitBeforeTax",
        "OperatingProfitBeforeProvisionAndContingencies",
        "ifrs-full:ProfitLossBeforeTax",
        "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxes",
        "us-gaap:IncomeLossBeforeIncomeTaxes",
    ],
    "pat": [
        "ProfitLossForThePeriod",
        "ProfitLossFromOrdinaryActivitiesAfterTax",
        "ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates",
        "ProfitLossForPeriod",
        "ProfitLossForPeriodFromContinuingOperations",
        "ifrs-full:ProfitLoss",
        "ifrs-full:NetIncomeLoss",
        "us-gaap:NetIncomeLoss",
        "us-gaap:NetIncomeLossAvailableToCommonStockholdersDiluted",
    ],
    "eps": [
        "DilutedEarningsPerShareAfterExtraordinaryItems",
        "BasicEarningsPerShareAfterExtraordinaryItems",
        "DilutedEarningsPerShareBeforeExtraordinaryItems",
        "BasicEarningsPerShareBeforeExtraordinaryItems",
        "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
        "BasicEarningsLossPerShareFromContinuingOperations",
        "BasicEarningsLossPerShare",
        "ifrs-full:BasicEarningsLossPerShare",
        "us-gaap:EarningsPerShareDiluted",
        "us-gaap:EarningsPerShareBasic",
    ],
    "total_assets": [
        "NetSegmentAssets",
        "SegmentAssets",
        "ifrs-full:Assets",
        "us-gaap:Assets",
    ],
    "current_assets": [
        "ifrs-full:CurrentAssets",
        "us-gaap:AssetsCurrent",
    ],
    "total_liabilities": [
        "NetSegmentLiabilities",
        "SegmentLiabilities",
        "ifrs-full:Liabilities",
        "us-gaap:Liabilities",
    ],
    "current_liabilities": [
        "ifrs-full:CurrentLiabilities",
        "us-gaap:LiabilitiesCurrent",
    ],
    "equity": [
        "ifrs-full:Equity",
        "ifrs-full:EquityAttributableToOwnersOfParent",
        "us-gaap:StockholdersEquity",
        "Equity",
    ],
    "total_debt": [
        "ifrs-full:NoncurrentFinancialLiabilities",
        "ifrs-full:FinancialLiabilities",
        "us-gaap:LongTermDebt",
        "us-gaap:DebtCurrent",
    ],
    "operating_cash_flow": [
        "NetCashFlowsFromUsedInOperatingActivities",
        "us-gaap:NetCashProvidedByUsedInOperatingActivities",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
        "ifrs-full:PurchaseOfPropertyPlantAndEquipment",
    ],
    "share_capital": [
        "PaidUpValueOfEquityShareCapital",
        "ifrs-full:EquityCapital",
        "us-gaap:CommonStock",
        "ifrs-full:ShareCapital",
    ],
    "face_value": [
        "FaceValueOfEquityShareCapital",
        "ifrs-full:FaceValue",
        "acfr:FaceValue",
    ],
}


class XBRLParser:
    """Parses XBRL inline or instance documents into normalized financials.

    Returns a dict keyed by standard field names. Values that cannot be
    resolved are left as None (N/A).
    """

    @classmethod
    def parse_file(cls, path: str) -> Dict[str, Any]:
        if path.lower().endswith(".html") or path.lower().endswith(".htm"):
            return cls._parse_inline(path)
        return cls._parse_instance(path)

    @classmethod
    def parse_bytes(cls, data: bytes, filename: str = "") -> Dict[str, Any]:
        import tempfile, os
        suffix = os.path.splitext(filename)[1] or ".xml"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            return cls.parse_file(tmp_path)
        finally:
            os.unlink(tmp_path)

    @classmethod
    def _parse_instance(cls, path: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        try:
            with open(path, "rb") as f:
                data = f.read()
            root = cls._get_root(data)
            return cls._extract_values(root)
        except Exception:
            return result

    @classmethod
    def _parse_inline(cls, path: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        try:
            from lxml import html as lxml_html
            tree = lxml_html.parse(path)
            root = tree.getroot()
            return cls._extract_values(root)
        except Exception:
            return result

    @classmethod
    def _get_root(cls, data: bytes):
        try:
            from lxml import etree
            parser = etree.XMLParser(recover=True, huge_tree=True)
            return etree.fromstring(data, parser)
        except Exception:
            try:
                import xml.etree.ElementTree as ET
                return ET.fromstring(data)
            except Exception:
                return None

    @classmethod
    def _extract_values(cls, root) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if root is None:
            return result

        for field, tags in XBRL_TAGS.items():
            val = cls._find_tag_value(root, tags, field)
            if val is not None:
                result[field] = val
        return result

    @staticmethod
    def _find_tag_value(root, tag_candidates, field_name: str = "") -> Optional[float]:
        for candidate in tag_candidates:
            target_local = candidate.split(":")[-1]
            for elem in root.iter():
                tag = elem.tag
                if not isinstance(tag, str):
                    continue
                local = tag.split("}")[-1] if "}" in tag else tag
                if local == target_local:
                    text = (elem.text or "").strip().replace(",", "")
                    if text:
                        try:
                            fval = float(text)
                            # Normalize rupees to Crores if field is monetary (not EPS/face_value) and fval > 100,000
                            if field_name not in ("eps", "face_value") and abs(fval) >= 100000:
                                fval = fval / 1e7
                            return fval
                        except ValueError:
                            continue
        return None
