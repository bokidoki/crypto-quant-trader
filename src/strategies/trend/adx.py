"""
趋势跟踪策略 - ADX
"""
from typing import Optional, Dict, List
from loguru import logger

from ..base import BaseStrategy, StrategyConfig
from ...exchanges.base import Ticker, KLine


class ADXStrategy(BaseStrategy):
    """
    ADX 趋势跟踪策略

    使用 ADX 指标判断趋势强度：
    - ADX > 25 且 +DI 上穿-DI → 买入做多
    - ADX > 25 且-DI 上穿+DI → 卖出做空
    - ADX < 20 → 市场无趋势，不交易

    参数:
        adx_period: ADX 周期，默认 14
        adx_threshold: ADX 阈值，默认 25
    """

    def __init__(self, config: StrategyConfig):
        super().__init__(config)

        self.adx_period = config.params.get("adx_period", 14)
        self.adx_threshold = config.params.get("adx_threshold", 25)

        self.last_plus_di = None
        self.last_minus_di = None

    async def on_tick(self, ticker: Ticker):
        self.ticker = ticker

    async def on_bar(self, bar: KLine):
        self.update_bar(bar)

    def _calc_adx(self, bars: List[KLine]) -> tuple:
        """计算 ADX、+DI、-DI"""
        if len(bars) < self.adx_period + 1:
            return 0.0, 0.0, 0.0

        plus_dms = []
        minus_dms = []
        trs = []

        for i in range(1, len(bars)):
            prev = bars[i - 1]
            curr = bars[i]

            # 计算 +DM 和-DM
            up_move = curr.high - prev.high
            down_move = prev.low - curr.low

            plus_dm = up_move if (up_move > down_move and up_move > 0) else 0
            minus_dm = down_move if (down_move > up_move and down_move > 0) else 0

            # 计算 TR
            tr = max(curr.high - curr.low, abs(curr.high - prev.close), abs(curr.low - prev.close))

            plus_dms.append(plus_dm)
            minus_dms.append(minus_dm)
            trs.append(tr)

        # 计算 smoothed +DM, -DM, TR
        smooth_plus = sum(plus_dms[-self.adx_period:])
        smooth_minus = sum(minus_dms[-self.adx_period:])
        smooth_tr = sum(trs[-self.adx_period:])

        # 计算 +DI 和-DI
        plus_di = (smooth_plus / smooth_tr * 100) if smooth_tr > 0 else 0
        minus_di = (smooth_minus / smooth_tr * 100) if smooth_tr > 0 else 0

        # 计算 DX
        di_sum = plus_di + minus_di
        di_diff = abs(plus_di - minus_di)
        dx = (di_diff / di_sum * 100) if di_sum > 0 else 0

        # ADX 是 DX 的平滑（这里简化为最近 N 个 DX 的平均）
        adx = dx  # 简化为当前 DX 值

        return adx, plus_di, minus_di

    async def generate_signal(self) -> Optional[Dict]:
        if len(self.bars) < self.adx_period + 1:
            return None

        adx, plus_di, minus_di = self._calc_adx(self.bars)

        signal = None

        # 只有在 ADX > 阈值时才交易（有趋势）
        if adx > self.adx_threshold:
            if self.last_plus_di is not None and self.last_minus_di is not None:
                # +DI 上穿-DI → 买入
                if self.last_plus_di <= self.last_minus_di and plus_di > minus_di:
                    signal = {
                        "side": "buy",
                        "amount": self.config.position_size,
                        "reason": f"ADX 趋势强：+DI({plus_di:.1f}) > -DI({minus_di:.1f}), ADX={adx:.1f}",
                    }
                    logger.info(f"📈 ADX 买入：{signal['reason']}")

                # -DI 上穿+DI → 卖出
                elif self.last_plus_di >= self.last_minus_di and plus_di < minus_di:
                    signal = {
                        "side": "sell",
                        "amount": self.config.position_size,
                        "reason": f"ADX 趋势强：-DI({minus_di:.1f}) > +DI({plus_di:.1f}), ADX={adx:.1f}",
                    }
                    logger.info(f"📉 ADX 卖出：{signal['reason']}")

        self.last_plus_di = plus_di
        self.last_minus_di = minus_di

        return signal

    def get_indicators(self) -> Dict:
        if len(self.bars) < self.adx_period + 1:
            return {}

        adx, plus_di, minus_di = self._calc_adx(self.bars)

        return {
            "adx": round(adx, 1),
            "plus_di": round(plus_di, 1),
            "minus_di": round(minus_di, 1),
            "trend_strength": "strong" if adx > self.adx_threshold else "weak",
        }
