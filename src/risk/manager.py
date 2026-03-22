"""
风控管理模块
"""
from typing import Dict, Optional, List
from datetime import datetime, date
from dataclasses import dataclass, field

from loguru import logger

from ..exchanges.base import Order, OrderSide
from ..core.config import get_settings


@dataclass
class RiskStats:
    """风控统计"""
    daily_pnl: float = 0.0
    daily_trades: int = 0
    total_positions: float = 0.0
    max_position_reached: float = 0.0
    date: date = field(default_factory=date.today)


class RiskManager:
    """
    风控管理器
    
    负责：
    - 仓位控制
    - 止损止盈检查
    - 每日亏损限制
    - 交易频率限制
    """
    
    def __init__(self):
        self.settings = get_settings().risk
        self.stats = RiskStats()
        self.orders: List[Order] = []
    
    def check_order(self, order: Order) -> tuple[bool, str]:
        """
        检查订单是否符合风控规则
        
        Args:
            order: 待检查的订单
            
        Returns:
            (是否通过, 原因)
        """
        # 检查每日亏损
        if self.stats.daily_pnl < -self.settings.max_daily_loss:
            return False, f"已达到每日最大亏损限制: {self.settings.max_daily_loss} USDT"
        
        # 检查仓位大小
        position_value = order.amount * (order.price or 0)
        if position_value > self.settings.max_position:
            return False, f"单笔仓位超过限制: {position_value:.2f} > {self.settings.max_position}"
        
        # 检查总仓位
        if self.stats.total_positions + position_value > self.settings.max_position * 3:
            return False, f"总仓位超过限制: {self.stats.total_positions + position_value:.2f}"
        
        return True, "通过"
    
    def update_position(self, order: Order):
        """更新仓位信息"""
        self.orders.append(order)
        
        if order.side == OrderSide.BUY:
            position_value = order.amount * (order.price or order.filled)
            self.stats.total_positions += position_value
        else:
            position_value = order.amount * (order.price or order.filled)
            self.stats.total_positions -= position_value
        
        self.stats.daily_trades += 1
        
        if self.stats.total_positions > self.stats.max_position_reached:
            self.stats.max_position_reached = self.stats.total_positions
    
    def update_pnl(self, pnl: float):
        """更新盈亏"""
        self.stats.daily_pnl += pnl
        logger.info(f"今日盈亏更新: {self.stats.daily_pnl:.2f} USDT")
    
    def check_stop_loss(self, entry_price: float, current_price: float, side: OrderSide) -> bool:
        """
        检查是否触发止损
        
        Args:
            entry_price: 入场价格
            current_price: 当前价格
            side: 持仓方向
            
        Returns:
            是否需要止损
        """
        if self.settings.stop_loss_percent <= 0:
            return False
        
        if side == OrderSide.BUY:
            # 多头止损：价格下跌超过阈值
            loss_percent = (entry_price - current_price) / entry_price * 100
            if loss_percent >= self.settings.stop_loss_percent:
                logger.warning(f"⚠️ 触发止损: 亏损 {loss_percent:.2f}%")
                return True
        else:
            # 空头止损：价格上涨超过阈值
            loss_percent = (current_price - entry_price) / entry_price * 100
            if loss_percent >= self.settings.stop_loss_percent:
                logger.warning(f"⚠️ 触发止损: 亏损 {loss_percent:.2f}%")
                return True
        
        return False
    
    def check_take_profit(self, entry_price: float, current_price: float, side: OrderSide) -> bool:
        """
        检查是否触发止盈
        
        Args:
            entry_price: 入场价格
            current_price: 当前价格
            side: 持仓方向
            
        Returns:
            是否需要止盈
        """
        if self.settings.take_profit_percent <= 0:
            return False
        
        if side == OrderSide.BUY:
            # 多头止盈：价格上涨超过阈值
            profit_percent = (current_price - entry_price) / entry_price * 100
            if profit_percent >= self.settings.take_profit_percent:
                logger.info(f"💰 触发止盈: 盈利 {profit_percent:.2f}%")
                return True
        else:
            # 空头止盈：价格下跌超过阈值
            profit_percent = (entry_price - current_price) / entry_price * 100
            if profit_percent >= self.settings.take_profit_percent:
                logger.info(f"💰 触发止盈: 盈利 {profit_percent:.2f}%")
                return True
        
        return False
    
    def reset_daily(self):
        """重置每日统计"""
        self.stats = RiskStats()
        logger.info("风控统计已重置")
    
    def get_stats(self) -> Dict:
        """获取风控统计"""
        return {
            "daily_pnl": self.stats.daily_pnl,
            "daily_trades": self.stats.daily_trades,
            "total_positions": self.stats.total_positions,
            "max_position_reached": self.stats.max_position_reached,
            "limits": {
                "max_position": self.settings.max_position,
                "max_daily_loss": self.settings.max_daily_loss,
                "stop_loss_percent": self.settings.stop_loss_percent,
                "take_profit_percent": self.settings.take_profit_percent,
            },
        }
