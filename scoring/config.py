from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScoringConfig:
    buy_threshold: int = 70
    sell_threshold: int = 40
    rsi_min: int = 50
    rsi_max: int = 70
    max_52w_distance: float = -10.0
    use_ma_trend: bool = True
    use_macd: bool = True
    use_volume: bool = True
    use_breakout: bool = True
    use_supertrend: bool = True
    technical_weight: float = 0.60
    fundamental_weight: float = 0.40


@dataclass
class TechnicalConfig:
    price_above_ma200_weight: int = 20
    ma50_above_ma200_weight: int = 15
    rsi_range_weight: int = 15
    macd_bullish_weight: int = 15
    near_52w_high_weight: int = 15
    breakout_weight: int = 10
    above_ma50_weight: int = 10
    volume_above_avg_weight: int = 10
    supertrend_bullish_weight: int = 10


@dataclass
class FundamentalConfig:
    eps_growth_weight: int = 20
    revenue_growth_weight: int = 20
    pat_growth_weight: int = 15
    roe_weight: int = 15
    roce_weight: int = 10
    roa_weight: int = 10
    debt_equity_weight: int = 10
    piotroski_weight: int = 10
    altman_weight: int = 10


@dataclass
class BankingConfig:
    nim_weight: int = 20
    nii_weight: int = 15
    casa_weight: int = 15
    gnpa_weight: int = 15
    nnpa_weight: int = 10
    pcr_weight: int = 10
    advances_growth_weight: int = 10
    deposits_growth_weight: int = 10
    car_weight: int = 10
    roa_weight: int = 15
    roe_weight: int = 15


@dataclass
class BacktestConfig:
    initial_capital: float = 100000.0
    start_date: Optional[str] = None
    transaction_cost: float = 0.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


@dataclass
class FundamentalThresholds:
    eps_growth_min: float = 0.10
    revenue_growth_min: float = 0.10
    pat_growth_min: float = 0.10
    roe_min: float = 0.15
    roce_min: float = 0.15
    roa_min: float = 0.05
    debt_equity_max: float = 100.0
    piotroski_min: int = 6
    altman_safe_threshold: float = 3.0
    altman_distress_threshold: float = 1.8


DEFAULT_CONFIG = ScoringConfig()
DEFAULT_TECHNICAL_CONFIG = TechnicalConfig()
DEFAULT_FUNDAMENTAL_CONFIG = FundamentalConfig()
DEFAULT_BANKING_CONFIG = BankingConfig()
DEFAULT_BACKTEST_CONFIG = BacktestConfig()
DEFAULT_FUNDAMENTAL_THRESHOLDS = FundamentalThresholds()


def score_category(percentage):
    if percentage >= 90:
        return "EXCELLENT"
    elif percentage >= 75:
        return "STRONG"
    elif percentage >= 60:
        return "GOOD"
    elif percentage >= 40:
        return "AVERAGE"
    else:
        return "WEAK"


def signal_badge(signal):
    if signal == "BUY":
        return "BUY"
    elif signal == "SELL":
        return "SELL"
    else:
        return "HOLD"
