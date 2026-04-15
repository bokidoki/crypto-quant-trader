"""
策略注册中心

用于注册和管理所有可用策略
"""
from typing import Dict, Type, List, Optional
from loguru import logger

from .base import BaseStrategy, StrategyConfig
from .trend import SMACrossStrategy, EMATrendStrategy, MACDStrategy, ADXStrategy
from .mean_reversion import BollingerStrategy, RSIReversionStrategy, KDJStrategy
from .momentum import RSIMomentumStrategy, ROCStrategy, WilliamsRStrategy


class StrategyRegistry:
    """策略注册中心"""

    # 策略注册表
    _strategies: Dict[str, Type[BaseStrategy]] = {
        # 趋势跟踪
        "sma_cross": SMACrossStrategy,
        "ema_trend": EMATrendStrategy,
        "macd": MACDStrategy,
        "adx": ADXStrategy,
        # 均值回归
        "bollinger": BollingerStrategy,
        "rsi_reversion": RSIReversionStrategy,
        "kdj": KDJStrategy,
        # 动量
        "rsi_momentum": RSIMomentumStrategy,
        "roc": ROCStrategy,
        "williams_r": WilliamsRStrategy,
    }

    @classmethod
    def register(cls, name: str, strategy_class: Type[BaseStrategy]):
        """注册新策略"""
        cls._strategies[name] = strategy_class
        logger.info(f"策略已注册：{name}")

    @classmethod
    def get(cls, name: str) -> Optional[Type[BaseStrategy]]:
        """获取策略类"""
        return cls._strategies.get(name)

    @classmethod
    def list_strategies(cls) -> List[str]:
        """列出所有可用策略"""
        return list(cls._strategies.keys())

    @classmethod
    def create_strategy(cls, name: str, config: StrategyConfig) -> Optional[BaseStrategy]:
        """创建策略实例"""
        strategy_class = cls.get(name)
        if strategy_class is None:
            logger.error(f"未知策略：{name}")
            return None

        return strategy_class(config)

    @classmethod
    def get_strategy_info(cls, name: str) -> Dict:
        """获取策略信息"""
        strategy_class = cls.get(name)
        if strategy_class is None:
            return {}

        return {
            "name": name,
            "class": strategy_class.__name__,
            "module": strategy_class.__module__,
            "category": cls._get_category(name),
        }

    @classmethod
    def _get_category(cls, name: str) -> str:
        """获取策略类别"""
        if name in ["sma_cross", "ema_trend", "macd", "adx"]:
            return "trend"
        elif name in ["bollinger", "rsi_reversion", "kdj"]:
            return "mean_reversion"
        elif name in ["rsi_momentum", "roc", "williams_r"]:
            return "momentum"
        return "unknown"


# 便捷函数
def get_strategy(name: str, config: StrategyConfig) -> Optional[BaseStrategy]:
    """创建策略实例"""
    return StrategyRegistry.create_strategy(name, config)


def list_strategies() -> List[str]:
    """列出所有可用策略"""
    return StrategyRegistry.list_strategies()
