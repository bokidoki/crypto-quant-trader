"""
均值回归策略 - 布林带
"""
from typing import Optional, Dict, List
from loguru import logger

from ..base import BaseStrategy, StrategyConfig
from ...exchanges.base import Ticker, KLine


class BollingerStrategy(BaseStrategy):
    """
    布林带均值回归策略

    当价格触及布林带下轨时买入，触及上轨时卖出：
    - 价格 < 下轨 → 买入（超卖）
    - 价格 > 上轨 → 卖出（超买）
    - 价格回归中轨 → 平仓

    参数:
        period: MA 周期，默认 20
        std_dev: 标准差倍数，默认 2.0
    """

    def __init__(self, config: StrategyConfig):
        super().__init__(config)

        self.period = config.params.get("period", 20)
        self.std_dev = config.params.get("std_dev", 2.0)

        self.last_position = None  # 记录最后仓位方向

    async def on_tick(self, ticker: Ticker):
        self.ticker = ticker

    async def on_bar(self, bar: KLine):
        self.update_bar(bar)

    def _calc_bollinger(self, prices: List[float]) -> tuple:
        """计算布林带"""
        if len(prices) < self.period:
            return 0.0, 0.0, 0.0

        # 中轨 = SMA
        middle = sum(prices[-self.period:]) / self.period

        # 标准差
        variance = sum((p - middle) ** 2 for p in prices[-self.period:]) / self.period
        std = variance ** 0.5

        # 上下轨
        upper = middle + self.std_dev * std
        lower = middle - self.std_dev * std

        return upper, middle, lower

    async def generate_signal(self) -> Optional[Dict]:
        if len(self.bars) < self.period:
            return None

        closes = [bar.close for bar in self.bars]
        current_price = closes[-1]
        upper, middle, lower = self._calc_bollinger(closes)

        signal = None

        # 价格低于下轨 → 超卖，买入
        if current_price < lower:
            if self.last_position != "long":
                signal = {
                    "side": "buy",
                    "amount": self.config.position_size,
                    "reason": f"价格 ({current_price:.2f}) < 布林下轨 ({lower:.2f})，超卖信号",
                }
                logger.info(f"📈 布林带买入：{signal['reason']}")
                self.last_position = "long"

        # 价格高于上轨 → 超买，卖出
        elif current_price > upper:
            if self.last_position != "short":
                signal = {
                    "side": "sell",
                    "amount": self.config.position_size,
                    "reason": f"价格 ({current_price:.2f}) > 布林上轨 ({upper:.2f})，超买信号",
                }
                logger.info(f"📉 布林带卖出：{signal['reason']}")
                self.last_position = "short"

        # 价格回归中轨 → 平仓信号
        elif self.positions:
            for pos in self.positions:
                if pos.status.value == "open":
                    # 多仓回归中轨
                    if pos.side.value == "buy" and current_price >= middle:
                        signal = {
                            "side": "sell",
                            "amount": pos.filled,
                            "reason": f"价格回归中轨 ({middle:.2f})，获利平仓",
                        }
                        logger.info(f"💰 布林带平仓：{signal['reason']}")
                        break
                    # 空仓回归中轨
                    elif pos.side.value == "sell" and current_price <= middle:
                        signal = {
                            "side": "buy",
                            "amount": pos.filled,
                            "reason": f"价格回归中轨 ({middle:.2f})，获利平仓",
                        }
                        logger.info(f"💰 布林带平仓：{signal['reason']}")
                        break

        return signal

    def get_indicators(self) -> Dict:
        if len(self.bars) < self.period:
            return {}

        closes = [bar.close for bar in self.bars]
        upper, middle, lower = self._calc_bollinger(closes)
        current_price = closes[-1]

        # 计算位置百分比
        bandwidth = upper - lower
        position = ((current_price - lower) / bandwidth * 100) if bandwidth > 0 else 50

        return {
            "upper": round(upper, 2),
            "middle": round(middle, 2),
            "lower": round(lower, 2),
            "price_position": f"{position:.1f}%",
        }
