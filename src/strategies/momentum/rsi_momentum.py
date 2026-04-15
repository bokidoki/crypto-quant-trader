"""
动量策略 - RSI 动量
"""
from typing import Optional, Dict, List
from loguru import logger

from ..base import BaseStrategy, StrategyConfig
from ...exchanges.base import Ticker, KLine


class RSIMomentumStrategy(BaseStrategy):
    """
    RSI 动量策略

    跟随 RSI 动量方向交易：
    - RSI 从下方上穿 50 → 买入（动量转强）
    - RSI 从上方下穿 50 → 卖出（动量转弱）
    - RSI 持续在 60 以上 → 持有多单
    - RSI 持续在 40 以下 → 持有空单

    参数:
        rsi_period: RSI 周期，默认 14
        momentum_threshold: 动量阈值，默认 50
    """

    def __init__(self, config: StrategyConfig):
        super().__init__(config)

        self.period = config.params.get("rsi_period", 14)
        self.threshold = config.params.get("momentum_threshold", 50)

        self.last_rsi = None

    async def on_tick(self, ticker: Ticker):
        self.ticker = ticker

    async def on_bar(self, bar: KLine):
        self.update_bar(bar)

    def _calc_rsi(self, prices: List[float]) -> float:
        """计算 RSI"""
        if len(prices) < self.period + 1:
            return 0.0

        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [c if c > 0 else 0 for c in changes]
        losses = [-c if c < 0 else 0 for c in changes]

        avg_gain = sum(gains[-self.period:]) / self.period
        avg_loss = sum(losses[-self.period:]) / self.period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    async def generate_signal(self) -> Optional[Dict]:
        if len(self.bars) < self.period + 1:
            return None

        closes = [bar.close for bar in self.bars]
        rsi = self._calc_rsi(closes)

        signal = None

        # RSI 上穿 50 中轴 → 动量转强，买入
        if self.last_rsi is not None:
            if self.last_rsi < self.threshold and rsi > self.threshold:
                signal = {
                    "side": "buy",
                    "amount": self.config.position_size,
                    "reason": f"RSI 动量转强：{self.last_rsi:.1f} → {rsi:.1f}，上穿{self.threshold}",
                }
                logger.info(f"📈 RSI 动量买入：{signal['reason']}")

            # RSI 下穿 50 中轴 → 动量转弱，卖出
            elif self.last_rsi > self.threshold and rsi < self.threshold:
                signal = {
                    "side": "sell",
                    "amount": self.config.position_size,
                    "reason": f"RSI 动量转弱：{self.last_rsi:.1f} → {rsi:.1f}，下穿{self.threshold}",
                }
                logger.info(f"📉 RSI 动量卖出：{signal['reason']}")

        self.last_rsi = rsi
        return signal

    def get_indicators(self) -> Dict:
        if len(self.bars) < self.period + 1:
            return {}

        closes = [bar.close for bar in self.bars]
        rsi = self._calc_rsi(closes)

        if rsi > 60:
            momentum = "strong_bullish"
        elif rsi > 50:
            momentum = "bullish"
        elif rsi > 40:
            momentum = "bearish"
        else:
            momentum = "strong_bearish"

        return {
            "rsi": round(rsi, 1),
            "momentum": momentum,
        }
