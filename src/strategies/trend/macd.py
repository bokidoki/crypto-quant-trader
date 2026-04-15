"""
趋势跟踪策略 - MACD
"""
from typing import Optional, Dict, List
from loguru import logger

from ..base import BaseStrategy, StrategyConfig
from ...exchanges.base import Ticker, KLine


class MACDStrategy(BaseStrategy):
    """
    MACD 趋势跟踪策略

    使用 MACD 指标判断趋势：
    - MACD 线上穿信号线（金叉）→ 买入
    - MACD 线下穿信号线（死叉）→ 卖出
    - MACD 柱状图由负转正 → 多头增强
    - MACD 柱状图由正转负 → 空头增强

    参数:
        fast_period: 快速 EMA 周期，默认 12
        slow_period: 慢速 EMA 周期，默认 26
        signal_period: 信号线周期，默认 9
    """

    def __init__(self, config: StrategyConfig):
        super().__init__(config)

        self.fast_period = config.params.get("fast_period", 12)
        self.slow_period = config.params.get("slow_period", 26)
        self.signal_period = config.params.get("signal_period", 9)

        self.last_macd = None
        self.last_signal = None
        self.last_histogram = None

    async def on_tick(self, ticker: Ticker):
        self.ticker = ticker

    async def on_bar(self, bar: KLine):
        self.update_bar(bar)

    def _calc_ema(self, prices: List[float], period: int) -> List[float]:
        """计算 EMA 序列"""
        if len(prices) < period:
            return []

        multiplier = 2 / (period + 1)
        ema = [sum(prices[:period]) / period]

        for price in prices[period:]:
            ema.append((price - ema[-1]) * multiplier + ema[-1])

        return ema

    def _calc_macd(self, prices: List[float]) -> tuple:
        """计算 MACD 值"""
        if len(prices) < self.slow_period:
            return 0.0, 0.0, 0.0

        ema_fast = self._calc_ema(prices, self.fast_period)
        ema_slow = self._calc_ema(prices, self.slow_period)

        # MACD 线 = 快速 EMA - 慢速 EMA
        macd_line = [f - s for f, s in zip(ema_fast[-len(ema_slow):], ema_slow)]

        # 信号线 = MACD 线的 EMA
        signal_line = self._calc_ema(macd_line, self.signal_period)

        # 柱状图
        histogram = macd_line[-1] - (signal_line[-1] if signal_line else 0)

        return macd_line[-1], signal_line[-1] if signal_line else 0, histogram

    async def generate_signal(self) -> Optional[Dict]:
        if len(self.bars) < self.slow_period + self.signal_period:
            return None

        closes = [bar.close for bar in self.bars]
        macd, signal, histogram = self._calc_macd(closes)

        result = None

        # 金叉：MACD 线上穿信号线
        if self.last_macd is not None and self.last_signal is not None:
            if self.last_macd <= self.last_signal and macd > signal:
                result = {
                    "side": "buy",
                    "amount": self.config.position_size,
                    "reason": f"MACD 金叉：MACD({macd:.2f}) > 信号线 ({signal:.2f})",
                }
                logger.info(f"📈 MACD 金叉买入")

            # 死叉：MACD 线下穿信号线
            elif self.last_macd >= self.last_signal and macd < signal:
                result = {
                    "side": "sell",
                    "amount": self.config.position_size,
                    "reason": f"MACD 死叉：MACD({macd:.2f}) < 信号线 ({signal:.2f})",
                }
                logger.info(f"📉 MACD 死叉卖出")

        self.last_macd = macd
        self.last_signal = signal
        self.last_histogram = histogram

        return result

    def get_indicators(self) -> Dict:
        if len(self.bars) < self.slow_period + self.signal_period:
            return {}

        closes = [bar.close for bar in self.bars]
        macd, signal, histogram = self._calc_macd(closes)

        return {
            "macd": round(macd, 2),
            "signal": round(signal, 2),
            "histogram": round(histogram, 2),
            "trend": "bullish" if macd > signal else "bearish",
        }
