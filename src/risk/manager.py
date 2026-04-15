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
class Position:
    """持仓信息"""
    symbol: str = ""
    amount: float = 0.0
    avg_price: float = 0.0
    side: str = "long"  # long 或 short


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
        self.positions: Dict[str, Position] = {}  # 每个交易对的持仓

    def check_order(self, order: Order) -> tuple[bool, str]:
        """
        检查订单是否符合风控规则

        Args:
            order: 待检查的订单

        Returns:
            (是否通过，原因)
        """
        # 检查每日亏损
        if self.stats.daily_pnl < -self.settings.max_daily_loss:
            return False, f"已达到每日最大亏损限制：{self.settings.max_daily_loss} USDT"

        # 检查仓位大小
        position_value = order.amount * (order.price or 0)
        if position_value > self.settings.max_position:
            return False, f"单笔仓位超过限制：{position_value:.2f} > {self.settings.max_position}"

        # 检查总仓位
        if self.stats.total_positions + position_value > self.settings.max_position * 3:
            return False, f"总仓位超过限制：{self.stats.total_positions + position_value:.2f}"

        return True, "通过"

    def update_position(self, order: Order, is_close: bool = False):
        """
        更新仓位信息

        Args:
            order: 订单
            is_close: 是否为平仓订单
        """
        self.orders.append(order)
        symbol = order.symbol

        if is_close:
            # 平仓订单：减少仓位，计算盈亏
            if symbol in self.positions:
                pos = self.positions[symbol]
                if pos.amount > 0:
                    # 计算盈亏
                    pnl = 0.0
                    if pos.side == "long":
                        # 多头平仓：卖出价格 - 买入均价
                        pnl = (order.filled - pos.avg_price) * order.amount
                    else:
                        # 空头平仓：买入价格 - 卖出均价（做空是高卖低买）
                        pnl = (pos.avg_price - order.filled) * order.amount

                    # 更新盈亏
                    self.stats.daily_pnl += pnl
                    logger.info(f"平仓盈亏：{pnl:.2f} USDT")

                    # 减少仓位
                    close_value = order.amount * order.filled
                    self.stats.total_positions -= close_value
                    pos.amount -= order.amount

                    if pos.amount <= 0:
                        del self.positions[symbol]
        else:
            # 开仓订单：增加仓位
            position_value = order.amount * (order.price or order.filled)

            if symbol not in self.positions:
                self.positions[symbol] = Position(
                    symbol=symbol,
                    amount=order.amount,
                    avg_price=order.price or order.filled,
                    side="long" if order.side == OrderSide.BUY else "short"
                )
            else:
                pos = self.positions[symbol]
                # 同方向加仓，更新平均成本
                if pos.side == ("long" if order.side == OrderSide.BUY else "short"):
                    total_cost = pos.avg_price * pos.amount + position_value
                    pos.amount += order.amount
                    pos.avg_price = total_cost / pos.amount if pos.amount > 0 else 0
                else:
                    # 反方向开仓，视为新开仓位
                    self.positions[symbol] = Position(
                        symbol=symbol,
                        amount=order.amount,
                        avg_price=order.price or order.filled,
                        side="long" if order.side == OrderSide.BUY else "short"
                    )

            self.stats.total_positions += position_value

        self.stats.daily_trades += 1

        if self.stats.total_positions > self.stats.max_position_reached:
            self.stats.max_position_reached = self.stats.total_positions

    def get_position(self, symbol: str) -> Optional[Position]:
        """获取指定交易对的持仓"""
        return self.positions.get(symbol)

    def update_pnl(self, pnl: float):
        """更新盈亏"""
        self.stats.daily_pnl += pnl
        logger.info(f"今日盈亏更新：{self.stats.daily_pnl:.2f} USDT")

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
                logger.warning(f"⚠️ 触发止损：亏损 {loss_percent:.2f}%")
                return True
        else:
            # 空头止损：价格上涨超过阈值
            loss_percent = (current_price - entry_price) / entry_price * 100
            if loss_percent >= self.settings.stop_loss_percent:
                logger.warning(f"⚠️ 触发止损：亏损 {loss_percent:.2f}%")
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
                logger.info(f"💰 触发止盈：盈利 {profit_percent:.2f}%")
                return True
        else:
            # 空头止盈：价格下跌超过阈值
            profit_percent = (entry_price - current_price) / entry_price * 100
            if profit_percent >= self.settings.take_profit_percent:
                logger.info(f"💰 触发止盈：盈利 {profit_percent:.2f}%")
                return True

        return False

    def reset_daily(self):
        """重置每日统计"""
        self.stats = RiskStats()
        self.positions.clear()
        logger.info("风控统计已重置")

    def get_stats(self) -> Dict:
        """获取风控统计"""
        return {
            "daily_pnl": self.stats.daily_pnl,
            "daily_trades": self.stats.daily_trades,
            "total_positions": self.stats.total_positions,
            "max_position_reached": self.stats.max_position_reached,
            # 前端需要的字段
            "win_rate": 0.0,  # 暂未实现胜率计算
            "max_drawdown": 0.0,  # 暂未实现最大回撤计算
            "max_position": self.settings.max_position,
            "stop_loss_percent": self.settings.stop_loss_percent,
            "take_profit_percent": self.settings.take_profit_percent,
            "max_daily_loss": self.settings.max_daily_loss,
        }
