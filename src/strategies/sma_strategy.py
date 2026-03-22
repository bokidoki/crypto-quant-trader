"""
简单移动平均策略示例
"""
from typing import Optional, Dict
from loguru import logger

from .base import BaseStrategy, StrategyConfig
from ..exchanges.base import Ticker, KLine


class SMAStrategy(BaseStrategy):
    """
    简单移动平均策略
    
    使用快速和慢速移动平均线交叉产生交易信号：
    - 快线 > 慢线 → 买入
    - 快线 < 慢线 → 卖出
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        
        # 策略参数
        self.fast_period = config.params.get("fast_period", 10)
        self.slow_period = config.params.get("slow_period", 30)
        
        # 上一次信号
        self.last_signal = None
        self.last_cross = None
    
    async def on_tick(self, ticker: Ticker):
        """行情更新"""
        self.ticker = ticker
    
    async def on_bar(self, bar: KLine):
        """K线更新"""
        self.update_bar(bar)
    
    async def generate_signal(self) -> Optional[Dict]:
        """生成交易信号"""
        # 需要足够的K线数据
        if len(self.bars) < self.slow_period:
            logger.debug(f"K线数量不足: {len(self.bars)} < {self.slow_period}")
            return None
        
        # 计算移动平均
        closes = [bar.close for bar in self.bars]
        
        fast_ma = sum(closes[-self.fast_period:]) / self.fast_period
        slow_ma = sum(closes[-self.slow_period:]) / self.slow_period
        
        # 判断交叉
        cross = "up" if fast_ma > slow_ma else "down"
        
        # 检测信号变化
        signal = None
        
        if self.last_cross is not None:
            if self.last_cross == "down" and cross == "up":
                # 金叉 → 买入
                signal = {
                    "side": "buy",
                    "amount": self.config.position_size,
                    "reason": f"金叉: 快线 {fast_ma:.2f} > 慢线 {slow_ma:.2f}",
                }
                logger.info(f"📈 金叉信号: {signal['reason']}")
            
            elif self.last_cross == "up" and cross == "down":
                # 死叉 → 卖出
                signal = {
                    "side": "sell",
                    "amount": self.config.position_size,
                    "reason": f"死叉: 快线 {fast_ma:.2f} < 慢线 {slow_ma:.2f}",
                }
                logger.info(f"📉 死叉信号: {signal['reason']}")
        
        self.last_cross = cross
        
        return signal
    
    def get_indicators(self) -> Dict:
        """获取当前指标值"""
        if len(self.bars) < self.slow_period:
            return {}
        
        closes = [bar.close for bar in self.bars]
        
        fast_ma = sum(closes[-self.fast_period:]) / self.fast_period
        slow_ma = sum(closes[-self.slow_period:]) / self.slow_period
        
        return {
            "fast_ma": fast_ma,
            "slow_ma": slow_ma,
            "trend": "up" if fast_ma > slow_ma else "down",
        }
