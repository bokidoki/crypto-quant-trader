"""
动量策略 - ROC 变化率
"""
from typing import Optional, Dict, List
from loguru import logger

from ..base import BaseStrategy, StrategyConfig
from ...exchanges.base import Ticker, KLine


class ROCStrategy(BaseStrategy):
    """
    ROC 动量策略

    使用价格变化率判断动量方向：
    - ROC 由负转正 → 买入（上涨动量）
    - ROC 由正转负 → 卖出（下跌动量）

    参数:
        roc_period: ROC 周期，默认 12
    """

    def __init__(self, config: StrategyConfig):
        super().__init__(config)

        self.period = config.params.get("roc_period", 12)
        self.last_roc = None

    async def on_tick(self, ticker: Ticker):
        self.ticker = ticker

    async def on_bar(self, bar: KLine):
        self.update_bar(bar)

    def _calc_roc(self, prices: List[float]) -> float:
        """计算 ROC (Rate of Change)"""
        if len(prices) <= self.period:
            return 0.0

        current = prices[-1]
        previous = prices[-self.period - 1]

        if previous == 0:
            return 0.0

        roc = (current - previous) / previous * 100
        return roc

    async def generate_signal(self) -> Optional[Dict]:
        if len(self.bars) < self.period + 1:
            return None

        closes = [bar.close for bar in self.bars]
        roc = self._calc_roc(closes)

        signal = None

        # ROC 由负转正 → 买入
        if self.last_roc is not None:
            if self.last_roc <= 0 and roc > 0:
                signal = {
                    "side": "buy",
                    "amount": self.config.position_size,
                    "reason": f"ROC 动量转正：{self.last_roc:.2f}% → {roc:.2f}%",
                }
                logger.info(f"📈 ROC 买入：{signal['reason']}")

            # ROC 由正转负 → 卖出
            elif self.last_roc >= 0 and roc < 0:
                signal = {
                    "side": "sell",
                    "amount": self.config.position_size,
                    "reason": f"ROC 动量转负：{self.last_roc:.2f}% → {roc:.2f}%",
                }
                logger.info(f"📉 ROC 卖出：{signal['reason']}")

        self.last_roc = roc
        return signal

    def get_indicators(self) -> Dict:
        if len(self.bars) < self.period + 1:
            return {}

        closes = [bar.close for bar in self.bars]
        roc = self._calc_roc(closes)

        return {
            "roc": round(roc, 2),
            "momentum": "positive" if roc > 0 else "negative",
        }
