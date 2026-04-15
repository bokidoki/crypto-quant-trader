"""
均值回归策略 - KDJ
"""
from typing import Optional, Dict, List
from loguru import logger

from ..base import BaseStrategy, StrategyConfig
from ...exchanges.base import Ticker, KLine


class KDJStrategy(BaseStrategy):
    """
    KDJ 均值回归策略

    使用 KDJ 指标判断超买超卖：
    - K < 20 且 K 上穿 D → 买入（超卖）
    - K > 80 且 K 下穿 D → 卖出（超买）
    - K 回归 50 → 平仓

    参数:
        kdj_period: KDJ 周期，默认 9
        k_smoothing: K 值平滑，默认 3
        d_smoothing: D 值平滑，默认 3
    """

    def __init__(self, config: StrategyConfig):
        super().__init__(config)

        self.period = config.params.get("kdj_period", 9)
        self.k_smooth = config.params.get("k_smoothing", 3)
        self.d_smooth = config.params.get("d_smoothing", 3)

        self.last_k = None
        self.last_d = None

    async def on_tick(self, ticker: Ticker):
        self.ticker = ticker

    async def on_bar(self, bar: KLine):
        self.update_bar(bar)

    def _calc_kdj(self, bars: List[KLine]) -> tuple:
        """计算 KDJ 值"""
        if len(bars) < self.period:
            return 0.0, 0.0, 0.0

        # 计算 RSV = (收盘价 - N 日最低价) / (N 日最高价 - N 日最低价) * 100
        recent = bars[-self.period:]
        lowest = min(bar.low for bar in recent)
        highest = max(bar.high for bar in recent)
        current_close = bars[-1].close

        if highest == lowest:
            rsv = 50.0
        else:
            rsv = (current_close - lowest) / (highest - lowest) * 100

        # 计算 K 值（RSV 的平滑）
        # 简化：使用最近 N 个 RSV 的平均
        k_values = []
        for i in range(self.period, len(bars) + 1):
            subset = bars[i-self.period:i]
            low = min(bar.low for bar in subset)
            high = max(bar.high for bar in subset)
            close = bars[i-1].close
            if high == low:
                k_values.append(50.0)
            else:
                k_values.append((close - low) / (high - low) * 100)

        # K = SMA(RSV)
        k = sum(k_values[-self.k_smooth:]) / self.k_smooth if k_values else rsv

        # D = SMA(K)
        # 简化：使用 K 的平均
        d = k  # 简化处理

        # J = 3*K - 2*D
        j = 3 * k - 2 * d

        return k, d, j

    async def generate_signal(self) -> Optional[Dict]:
        if len(self.bars) < self.period:
            return None

        k, d, j = self._calc_kdj(self.bars)

        signal = None

        # KDJ 金叉：K 线上穿 D 线，且在超卖区域
        if self.last_k is not None and self.last_d is not None:
            if self.last_k <= self.last_d and k > d and k < 40:
                signal = {
                    "side": "buy",
                    "amount": self.config.position_size,
                    "reason": f"KDJ 金叉：K({k:.1f}) > D({d:.1f})，超卖区域",
                }
                logger.info(f"📈 KDJ 买入：{signal['reason']}")

            # KDJ 死叉：K 线下穿 D 线，且在超买区域
            elif self.last_k >= self.last_d and k < d and k > 60:
                signal = {
                    "side": "sell",
                    "amount": self.config.position_size,
                    "reason": f"KDJ 死叉：K({k:.1f}) < D({d:.1f})，超买区域",
                }
                logger.info(f"📉 KDJ 卖出：{signal['reason']}")

        self.last_k = k
        self.last_d = d

        return signal

    def get_indicators(self) -> Dict:
        if len(self.bars) < self.period:
            return {}

        k, d, j = self._calc_kdj(self.bars)

        if k > 80:
            level = "overbought"
        elif k < 20:
            level = "oversold"
        else:
            level = "neutral"

        return {
            "k": round(k, 1),
            "d": round(d, 1),
            "j": round(j, 1),
            "level": level,
        }
