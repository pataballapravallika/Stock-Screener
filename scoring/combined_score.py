from typing import Optional
from scoring.config import (
    ScoringConfig,
    DEFAULT_CONFIG,
)
from scoring.technical_score import score_technical
from scoring.fundamental_score import score_fundamental
from scoring.banking_score import score_banking


def combined_score(
    row: Optional[dict] = None,
    technical_result: Optional[dict] = None,
    fundamental_result: Optional[dict] = None,
    banking_result: Optional[dict] = None,
    config: Optional[ScoringConfig] = None,
    is_bank: bool = False,
) -> dict:
    if config is None:
        config = DEFAULT_CONFIG

    if technical_result is None and row is not None:
        technical_result = score_technical(row, config=config)

    if fundamental_result is None and row is not None and not is_bank:
        fund_data = row.get("fundamentals", {})
        fundamental_result = score_fundamental(fund_data, config=config)

    if banking_result is None and row is not None and is_bank:
        bank_data = row.get("banking_fundamentals", {})
        banking_result = score_banking(bank_data, config=config)

    if fundamental_result is None:
        fundamental_result = {"score": 0, "max_score": 100, "percentage": 0.0, "signal": "HOLD"}
    if banking_result is None:
        banking_result = {"score": 0, "max_score": 100, "percentage": 0.0, "signal": "HOLD"}

    tech_pct = technical_result.get("percentage", 0.0) if technical_result else 0.0
    fund_pct = fundamental_result.get("percentage", 0.0) if fundamental_result else 0.0
    bank_pct = banking_result.get("percentage", 0.0) if banking_result else 0.0

    if is_bank:
        combined_pct = (
            tech_pct * config.technical_weight +
            bank_pct * config.fundamental_weight
        )
        fund_signal = banking_result.get("signal", "HOLD")
    else:
        combined_pct = (
            tech_pct * config.technical_weight +
            fund_pct * config.fundamental_weight
        )
        fund_signal = fundamental_result.get("signal", "HOLD")

    if combined_pct >= config.buy_threshold:
        signal = "BUY"
    elif combined_pct >= config.sell_threshold:
        signal = "HOLD"
    else:
        signal = "SELL"

    return {
        "technical": technical_result,
        "fundamental": fundamental_result,
        "banking": banking_result,
        "combined_percentage": round(combined_pct, 2),
        "combined_signal": signal,
        "technical_weight": config.technical_weight,
        "fundamental_weight": config.fundamental_weight,
        "is_bank": is_bank,
        "fundamental_signal": fund_signal,
    }
