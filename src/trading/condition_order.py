"""
条件单引擎

支持条件单的创建、监控、触发和执行
"""
from typing import Dict, List, Optional, Callable
from datetime import datetime
from decimal import Decimal
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger


class ConditionType(str, Enum):
    """条件类型"""
    PRICE_ABOVE = "price_above"       # 价格突破
    PRICE_BELOW = "price_below"       # 价格跌破
    PRICE_CROSS_ABOVE = "price_cross_above"  # 价格上穿
    PRICE_CROSS_BELOW = "price_cross_below"  # 价格下穿


class TriggerType(str, Enum):
    """触发类型"""
    ONCE = "once"           # 单次触发
    REPEATING = "repeating" # 重复触发


@dataclass
class ConditionOrder:
    """
    条件单数据类

    条件单包含:
    - 触发条件（价格突破/跌破等）
    - 执行订单（市价单/限价单）
    - 可选的止盈止损
    """
    id: str
    symbol: str
    condition_type: ConditionType
    trigger_price: Decimal      # 触发价格
    current_price: Decimal      # 当前价格（用于监控）
    order_side: str             # 执行订单方向
    order_amount: Decimal       # 执行订单数量
    order_type: str = "market"  # 执行订单类型
    order_price: Optional[Decimal] = None  # 执行订单价格（限价单需要）

    # 止盈止损
    take_profit: Optional[Decimal] = None  # 止盈价
    stop_loss: Optional[Decimal] = None    # 止损价

    # 状态
    is_active: bool = True
    trigger_type: TriggerType = TriggerType.ONCE
    triggered_count: int = 0
    max_triggers: int = 1  # 最大触发次数

    # 时间
    created_at: datetime = field(default_factory=datetime.now)
    last_triggered_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None  # 过期时间

    # 执行结果
    executed_order_id: Optional[str] = None

    def check_condition(self, current_price: Decimal) -> bool:
        """
        检查条件是否满足

        Args:
            current_price: 当前价格

        Returns:
            是否满足触发条件
        """
        if not self.is_active:
            return False

        # 检查是否过期
        if self.expires_at and datetime.now() > self.expires_at:
            self.is_active = False
            return False

        # 检查触发次数
        if self.triggered_count >= self.max_triggers:
            self.is_active = False
            return False

        # 根据条件类型检查
        if self.condition_type == ConditionType.PRICE_ABOVE:
            return current_price >= self.trigger_price

        elif self.condition_type == ConditionType.PRICE_BELOW:
            return current_price <= self.trigger_price

        elif self.condition_type == ConditionType.PRICE_CROSS_ABOVE:
            # 价格上穿：之前低于触发价，现在高于
            crossed = self.current_price < self.trigger_price and current_price >= self.trigger_price
            self.current_price = current_price
            return crossed

        elif self.condition_type == ConditionType.PRICE_CROSS_BELOW:
            # 价格下穿：之前高于触发价，现在低于
            crossed = self.current_price > self.trigger_price and current_price <= self.trigger_price
            self.current_price = current_price
            return crossed

        return False

    def trigger(self):
        """标记条件单已触发"""
        self.triggered_count += 1
        self.last_triggered_at = datetime.now()

        if self.trigger_type == TriggerType.ONCE:
            self.is_active = False
        elif self.triggered_count >= self.max_triggers:
            self.is_active = False


class ConditionOrderEngine:
    """
    条件单引擎

    功能:
    - 创建条件单
    - 监控价格并触发条件单
    - 执行条件单
    - 止盈止损联动
    """

    def __init__(self, order_manager=None, price_feed=None):
        """
        初始化条件单引擎

        Args:
            order_manager: 订单管理器
            price_feed: 价格源（提供实时价格）
        """
        self.order_manager = order_manager
        self.price_feed = price_feed
        self._condition_orders: Dict[str, ConditionOrder] = {}
        self._callbacks: List[Callable] = []  # 触发回调

    def create_condition_order(
        self,
        symbol: str,
        condition_type: str,
        trigger_price: float,
        order_side: str,
        order_amount: float,
        order_type: str = "market",
        order_price: Optional[float] = None,
        take_profit: Optional[float] = None,
        stop_loss: Optional[float] = None,
        trigger_type: str = "once",
        max_triggers: int = 1,
        expires_hours: Optional[int] = None,
    ) -> ConditionOrder:
        """
        创建条件单

        Args:
            symbol: 交易对
            condition_type: 条件类型 (price_above/price_below/price_cross_above/price_cross_below)
            trigger_price: 触发价格
            order_side: 执行订单方向 (buy/sell)
            order_amount: 执行订单数量
            order_type: 执行订单类型 (market/limit)
            order_price: 执行订单价格（限价单需要）
            take_profit: 止盈价
            stop_loss: 止损价
            trigger_type: 触发类型 (once/repeating)
            max_triggers: 最大触发次数
            expires_hours: 过期时间（小时）

        Returns:
            条件单对象
        """
        import uuid

        condition_order = ConditionOrder(
            id=str(uuid.uuid4())[:8],
            symbol=symbol,
            condition_type=ConditionType(condition_type),
            trigger_price=Decimal(str(trigger_price)),
            current_price=Decimal(str(trigger_price)),  # 初始化为触发价
            order_side=order_side,
            order_amount=Decimal(str(order_amount)),
            order_type=order_type,
            order_price=Decimal(str(order_price)) if order_price else None,
            take_profit=Decimal(str(take_profit)) if take_profit else None,
            stop_loss=Decimal(str(stop_loss)) if stop_loss else None,
            trigger_type=TriggerType(trigger_type),
            max_triggers=max_triggers,
        )

        # 设置过期时间
        if expires_hours:
            from datetime import timedelta
            condition_order.expires_at = datetime.now() + timedelta(hours=expires_hours)

        # 保存到内存
        self._condition_orders[condition_order.id] = condition_order
        logger.info(
            f"创建条件单：{condition_order.id} {symbol} "
            f"{condition_type}={trigger_price} -> {order_side} {order_amount}"
        )

        return condition_order

    async def check_conditions(self, symbol: Optional[str] = None):
        """
        检查所有条件单

        Args:
            symbol: 指定交易对，None 检查所有
        """
        for order_id, condition_order in list(self._condition_orders.items()):
            if not condition_order.is_active:
                continue

            if symbol and condition_order.symbol != symbol:
                continue

            # 获取当前价格
            current_price = await self._get_current_price(condition_order.symbol)
            if current_price is None:
                continue

            current_price = Decimal(str(current_price))

            # 检查条件
            if condition_order.check_condition(current_price):
                logger.info(
                    f"条件单触发：{order_id} {condition_order.symbol} "
                    f"当前价={current_price}, 触发价={condition_order.trigger_price}"
                )

                # 触发条件单
                condition_order.trigger()

                # 执行订单
                await self._execute_condition_order(condition_order)

                # 通知回调
                for callback in self._callbacks:
                    try:
                        await callback(condition_order)
                    except Exception as e:
                        logger.error(f"条件单回调失败：{e}")

    async def _get_current_price(self, symbol: str) -> Optional[float]:
        """获取当前价格"""
        if self.price_feed:
            return await self.price_feed.get_price(symbol)

        # 如果没有价格源，尝试从交易所获取
        if self.order_manager and self.order_manager.exchange_manager:
            try:
                ticker = await self.order_manager.exchange_manager.get_ticker(symbol)
                return ticker.get("last") if ticker else None
            except Exception as e:
                logger.error(f"获取价格失败：{e}")
                return None

        return None

    async def _execute_condition_order(self, condition_order: ConditionOrder):
        """
        执行条件单

        Args:
            condition_order: 条件单对象
        """
        if not self.order_manager:
            logger.error("订单管理器未设置")
            return

        # 创建并执行订单
        order = self.order_manager.create_order(
            symbol=condition_order.symbol,
            side=condition_order.order_side,
            amount=float(condition_order.order_amount),
            order_type=condition_order.order_type,
            price=float(condition_order.order_price) if condition_order.order_price else None,
        )

        success = await self.order_manager.submit_order(order)

        if success:
            condition_order.executed_order_id = order.id
            logger.info(f"条件单执行成功：{condition_order.id} -> 订单 {order.id}")

            # 如果有止盈止损，创建关联条件单
            if condition_order.take_profit:
                await self._create_tp_sl_order(
                    condition_order,
                    "take_profit",
                    condition_order.take_profit,
                )
            if condition_order.stop_loss:
                await self._create_tp_sl_order(
                    condition_order,
                    "stop_loss",
                    condition_order.stop_loss,
                )
        else:
            logger.error(f"条件单执行失败：{condition_order.id}")

    async def _create_tp_sl_order(
        self,
        parent_order: ConditionOrder,
        tp_sl_type: str,
        price: Decimal,
    ):
        """
        创建止盈止损条件单

        Args:
            parent_order: 父订单
            tp_sl_type: 类型 (take_profit/stop_loss)
            price: 触发价格
        """
        # 确定止盈止损的方向
        if parent_order.order_side == "buy":
            # 多单：止盈向上，止损向下
            if tp_sl_type == "take_profit":
                condition_type = ConditionType.PRICE_ABOVE
            else:
                condition_type = ConditionType.PRICE_BELOW
            close_side = "sell"
        else:
            # 空单：止盈向下，止损向上
            if tp_sl_type == "take_profit":
                condition_type = ConditionType.PRICE_BELOW
            else:
                condition_type = ConditionType.PRICE_ABOVE
            close_side = "buy"

        tp_sl_order = self.create_condition_order(
            symbol=parent_order.symbol,
            condition_type=condition_type.value,
            trigger_price=float(price),
            order_side=close_side,
            order_amount=float(parent_order.order_amount),
            order_type="market",
            trigger_type=TriggerType.ONCE,
        )

        logger.info(
            f"创建{tp_sl_type}条件单：{tp_sl_order.id} "
            f"{parent_order.symbol} @ {price}"
        )

    def get_active_orders(self, symbol: Optional[str] = None) -> List[ConditionOrder]:
        """获取所有活动条件单"""
        orders = [o for o in self._condition_orders.values() if o.is_active]
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        return orders

    def get_order(self, order_id: str) -> Optional[ConditionOrder]:
        """获取条件单"""
        return self._condition_orders.get(order_id)

    def cancel_order(self, order_id: str) -> bool:
        """取消条件单"""
        order = self._condition_orders.get(order_id)
        if not order:
            return False
        order.is_active = False
        logger.info(f"条件单已取消：{order_id}")
        return True

    def register_callback(self, callback: Callable):
        """注册触发回调"""
        self._callbacks.append(callback)
