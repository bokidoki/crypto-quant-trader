"""
趋势跟踪策略 - EMA 趋势
"""
from typing import Optional, Dict
from loguru import logger

from ..base import BaseStrategy, StrategyConfig
from ...exchanges.base import Ticker, KLine


class EMATrendStrategy(BaseStrategy):
    """
    EMA 趋势跟踪策略

    使用指数移动平均线判断趋势方向：
    - 价格上穿 EMA20 → 买入做多
    - 价格下穿 EMA20 → 卖出做空
    - EMA20 > EMA50 → 多头趋势增强
    - EMA20 < EMA50 → 空头趋势增强

    参数:
        ema_fast: 快速 EMA 周期，默认 20
        ema_slow: 慢速 EMA 周期，默认 50
    """

    def __init__(self, config: StrategyConfig):
        super().__init__(config)

        self.ema_fast = config.params.get("ema_fast", 20)
        self.ema_slow = config.params.get("ema_slow", 50)

        self.last_signal = None

    async def on_tick(self, ticker: Ticker):
        self.ticker = ticker

    async def on_bar(self, bar: KLine):
        self.update_bar(bar)

    def _calc_ema(self, prices: list, period: int) -> float:
        """计算指数移动平均"""
        if len(prices) < period:
            return 0.0

        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period  # 初始 SMA

        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema

        return ema

    async def generate_signal(self) -> Optional[Dict]:
        if len(self.bars) < self.ema_slow:
            return None

        closes = [bar.close for bar in self.bars]
        current_price = closes[-1]

        ema_f = self._calc_ema(closes, self.ema_fast)
        ema_s = self._calc_ema(closes, self.ema_slow)

        signal = None

        # 价格上穿 EMA 快线
        if len(closes) > 1:
            prev_price = closes[-2]

            if prev_price <= ema_f and current_price > ema_f:
                # 确认趋势：EMA 快线在慢线上方
                if ema_f > ema_s:
                    signal = {
                        "side": "buy",
                        "amount": self.config.position_size,
                        "reason": f"价格上穿 EMA{self.ema_fast}，多头趋势",
                    }
                    logger.info(f"📈 EMA 买入：{signal['reason']}")

            elif prev_price >= ema_f and current_price < ema_f:
                # 价格下穿 EMA 快线
                if ema_f < ema_s:
                    signal = {
                        "side": "sell",
                        "amount": self.config.position_size,
                        "reason": f"价格下穿 EMA{self.ema_fast}，空头趋势",
                    }
                    logger.info(f"📉 EMA 卖出：{signal['reason']}")

        return signal

    def get_indicators(self) -> Dict:
        if len(self.bars) < self.ema_slow:
            return {}

        closes = [bar.close for bar in self.bars]
        ema_f = self._calc_ema(closes, self.ema_fast)
        ema_s = self._calc_ema(closes, self.ema_slow)

        return {
            "ema_fast": round(ema_f, 2),
            "ema_slow": round(ema_s, 2),
            "trend": "bullish" if ema_f > ema_s else "bearish",
        }
