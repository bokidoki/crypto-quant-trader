"""
策略模块

提供 9 个策略模板，分为三大类：
- 趋势跟踪：SMA 交叉、EMA 趋势、MACD、ADX
- 均值回归：布林带、RSI 极值、KDJ
- 动量：RSI 动量、ROC、威廉指标
"""
from .base import BaseStrategy, StrategyConfig
from .registry import StrategyRegistry, get_strategy, list_strategies

# 趋势跟踪策略
from .trend import SMACrossStrategy, EMATrendStrategy, MACDStrategy, ADXStrategy
# 均值回归策略
from .mean_reversion import BollingerStrategy, RSIReversionStrategy, KDJStrategy
# 动量策略
from .momentum import RSIMomentumStrategy, ROCStrategy, WilliamsRStrategy

__all__ = [
    # 基类和配置
    "BaseStrategy",
    "StrategyConfig",
    # 注册中心
    "StrategyRegistry",
    "get_strategy",
    "list_strategies",
    # 趋势跟踪
    "SMACrossStrategy",
    "EMATrendStrategy",
    "MACDStrategy",
    "ADXStrategy",
    # 均值回归
    "BollingerStrategy",
    "RSIReversionStrategy",
    "KDJStrategy",
    # 动量
    "RSIMomentumStrategy",
    "ROCStrategy",
    "WilliamsRStrategy",
]
