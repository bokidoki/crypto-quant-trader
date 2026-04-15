"""
趋势跟踪策略包
"""
from .sma_cross import SMACrossStrategy
from .ema_trend import EMATrendStrategy
from .macd import MACDStrategy
from .adx import ADXStrategy

__all__ = [
    "SMACrossStrategy",
    "EMATrendStrategy",
    "MACDStrategy",
    "ADXStrategy",
]
