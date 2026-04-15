"""
均值回归策略 - RSI 极值
"""
from typing import Optional, Dict, List
from loguru import logger

from ..base import BaseStrategy, StrategyConfig
from ...exchanges.base import Ticker, KLine


class RSIReversionStrategy(BaseStrategy):
    """
    RSI 均值回归策略

    当 RSI 进入超卖区域时买入，进入超买区域时卖出：
    - RSI < 30 → 买入（超卖）
    - RSI > 70 → 卖出（超买）
    - RSI 回归 50 → 平仓

    参数:
        rsi_period: RSI 周期，默认 14
        oversold: 超卖阈值，默认 30
        overbought: 超买阈值，默认 70
    """

    def __init__(self, config: StrategyConfig):
        super().__init__(config)

        self.period = config.params.get("rsi_period", 14)
        self.oversold = config.params.get("oversold", 30)
        self.overbought = config.params.get("overbought", 70)

        self.last_rsi = None

    async def on_tick(self, ticker: Ticker):
        self.ticker = ticker

    async def on_bar(self, bar: KLine):
        self.update_bar(bar)

    def _calc_rsi(self, prices: List[float]) -> float:
        """计算 RSI"""
        if len(prices) < self.period + 1:
            return 0.0

        # 计算价格变化
        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]

        # 分离涨跌
        gains = [c if c > 0 else 0 for c in changes]
        losses = [-c if c < 0 else 0 for c in changes]

        # 平均涨跌幅
        avg_gain = sum(gains[-self.period:]) / self.period
        avg_loss = sum(losses[-self.period:]) / self.period

        # 计算 RS 和 RSI
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

        # RSI 从超卖区域回升
        if self.last_rsi is not None:
            if self.last_rsi < self.oversold and rsi >= self.oversold:
                signal = {
                    "side": "buy",
                    "amount": self.config.position_size,
                    "reason": f"RSI 超卖反弹：{self.last_rsi:.1f} → {rsi:.1f}",
                }
                logger.info(f"📈 RSI 买入：{signal['reason']}")

            # RSI 从超买区域回落
            elif self.last_rsi > self.overbought and rsi <= self.overbought:
                signal = {
                    "side": "sell",
                    "amount": self.config.position_size,
                    "reason": f"RSI 超买回落：{self.last_rsi:.1f} → {rsi:.1f}",
                }
                logger.info(f"📉 RSI 卖出：{signal['reason']}")

        # 已有仓位，检查是否回归中性
        elif self.positions:
            for pos in self.positions:
                if pos.status.value == "open":
                    # 多仓：RSI 回归 50 以上
                    if pos.side.value == "buy" and rsi >= 50:
                        signal = {
                            "side": "sell",
                            "amount": pos.filled,
                            "reason": f"RSI 回归中性 ({rsi:.1f})，获利平仓",
                        }
                        logger.info(f"💰 RSI 平仓：{signal['reason']}")
                        break
                    # 空仓：RSI 回归 50 以下
                    elif pos.side.value == "sell" and rsi <= 50:
                        signal = {
                            "side": "buy",
                            "amount": pos.filled,
                            "reason": f"RSI 回归中性 ({rsi:.1f})，获利平仓",
                        }
                        logger.info(f"💰 RSI 平仓：{signal['reason']}")
                        break

        self.last_rsi = rsi
        return signal

    def get_indicators(self) -> Dict:
        if len(self.bars) < self.period + 1:
            return {}

        closes = [bar.close for bar in self.bars]
        rsi = self._calc_rsi(closes)

        if rsi >= self.overbought:
            level = "overbought"
        elif rsi <= self.oversold:
            level = "oversold"
        else:
            level = "neutral"

        return {
            "rsi": round(rsi, 1),
            "level": level,
        }
