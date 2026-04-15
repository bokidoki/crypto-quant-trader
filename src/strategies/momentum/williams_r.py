"""
动量策略 - 威廉指标
"""
from typing import Optional, Dict, List
from loguru import logger

from ..base import BaseStrategy, StrategyConfig
from ...exchanges.base import Ticker, KLine


class WilliamsRStrategy(BaseStrategy):
    """
    威廉指标动量策略

    使用 Williams %R 指标判断超买超卖：
    - %R > -20 → 超买，卖出
    - %R < -80 → 超卖，买入
    - %R 从超卖区回升 → 买入确认
    - %R 从超买区回落 → 卖出确认

    参数:
        wr_period: 威廉指标周期，默认 14
    """

    def __init__(self, config: StrategyConfig):
        super().__init__(config)

        self.period = config.params.get("wr_period", 14)
        self.overbought = -20  # 超买线
        self.oversold = -80    # 超卖线

        self.last_wr = None

    async def on_tick(self, ticker: Ticker):
        self.ticker = ticker

    async def on_bar(self, bar: KLine):
        self.update_bar(bar)

    def _calc_williams_r(self, bars: List[KLine]) -> float:
        """计算威廉指标"""
        if len(bars) < self.period:
            return -50.0  # 中性值

        recent = bars[-self.period:]
        highest = max(bar.high for bar in recent)
        lowest = min(bar.low for bar in recent)
        current_close = bars[-1].close

        if highest == lowest:
            return -50.0

        # Williams %R = (最高价 - 收盘价) / (最高价 - 最低价) * -100
        wr = (highest - current_close) / (highest - lowest) * -100

        return wr

    async def generate_signal(self) -> Optional[Dict]:
        if len(self.bars) < self.period:
            return None

        wr = self._calc_williams_r(self.bars)

        signal = None

        # 从超卖区回升
        if self.last_wr is not None:
            if self.last_wr < self.oversold and wr >= self.oversold:
                signal = {
                    "side": "buy",
                    "amount": self.config.position_size,
                    "reason": f"威廉指标超卖反弹：{self.last_wr:.1f} → {wr:.1f}",
                }
                logger.info(f"📈 威廉指标买入：{signal['reason']}")

            # 从超买区回落
            elif self.last_wr > self.overbought and wr <= self.overbought:
                signal = {
                    "side": "sell",
                    "amount": self.config.position_size,
                    "reason": f"威廉指标超买回落：{self.last_wr:.1f} → {wr:.1f}",
                }
                logger.info(f"📉 威廉指标卖出：{signal['reason']}")

        self.last_wr = wr
        return signal

    def get_indicators(self) -> Dict:
        if len(self.bars) < self.period:
            return {}

        wr = self._calc_williams_r(self.bars)

        if wr > self.overbought:
            level = "overbought"
        elif wr < self.oversold:
            level = "oversold"
        else:
            level = "neutral"

        return {
            "williams_r": round(wr, 1),
            "level": level,
        }
