"""
分析中心模块

提供绩效分析、交易分析、资金曲线、持仓分析、策略对比等功能
"""
from .performance.metrics import PerformanceMetrics
from .trades.win_rate import TradeAnalyzer
from .capital.curve import CapitalCurveAnalyzer
from .position.analysis import PositionAnalyzer
from .strategy.comparison import StrategyComparator

__all__ = [
    "PerformanceMetrics",
    "TradeAnalyzer",
    "CapitalCurveAnalyzer",
    "PositionAnalyzer",
    "StrategyComparator",
]
