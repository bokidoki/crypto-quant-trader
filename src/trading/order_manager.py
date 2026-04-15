"""
订单管理器

提供订单创建、修改、取消等功能
"""
from typing import Dict, List, Optional
from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger


class OrderType(str, Enum):
    """订单类型"""
    MARKET = "market"       # 市价单
    LIMIT = "limit"         # 限价单
    STOP_MARKET = "stop_market"     # 止损市价单
    STOP_LIMIT = "stop_limit"       # 止损限价单
    TAKE_PROFIT_MARKET = "take_profit_market"   # 止盈市价单
    TAKE_PROFIT_LIMIT = "take_profit_limit"     # 止盈限价单


class OrderStatus(str, Enum):
    """订单状态"""
    PENDING = "pending"     # 待处理
    OPEN = "open"           # 已挂单
    PARTIALLY_FILLED = "partially_filled"  # 部分成交
    FILLED = "filled"       # 已成交
    CANCELLED = "cancelled" # 已取消
    REJECTED = "rejected"   # 已拒绝


@dataclass
class Order:
    """订单数据类"""
    id: str
    symbol: str
    side: str  # buy/sell
    order_type: OrderType
    amount: Decimal
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None  # 止损/止盈触发价
    filled: Decimal = Decimal("0")
    remaining: Decimal = Decimal("0")
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    exchange_order_id: Optional[str] = None  # 交易所订单 ID

    def __post_init__(self):
        if self.remaining == 0 and self.amount > 0:
            self.remaining = self.amount

    @property
    def fill_rate(self) -> float:
        """成交率"""
        if self.amount <= 0:
            return 0.0
        return float(self.filled / self.amount * 100)

    def is_active(self) -> bool:
        """订单是否有效（可撤销）"""
        return self.status in [OrderStatus.PENDING, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]


class OrderManager:
    """
    订单管理器

    功能:
    - 创建订单（市价单、限价单、条件单）
    - 修改订单
    - 取消订单
    - 查询订单状态
    - 订单持久化
    """

    def __init__(self, exchange_manager=None, db_manager=None):
        """
        初始化订单管理器

        Args:
            exchange_manager: 交易所管理器
            db_manager: 数据库管理器
        """
        self.exchange_manager = exchange_manager
        self.db_manager = db_manager
        self._orders: Dict[str, Order] = {}  # 内存订单缓存

    def create_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        order_type: str = "market",
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> Order:
        """
        创建订单

        Args:
            symbol: 交易对
            side: 方向 (buy/sell)
            amount: 数量
            order_type: 订单类型 (market/limit/stop_market/stop_limit/take_profit_market/take_profit_limit)
            price: 价格（限价单/止损限价单需要）
            stop_price: 触发价（止损/止盈单需要）

        Returns:
            订单对象
        """
        import uuid

        order_id = str(uuid.uuid4())[:8]

        order = Order(
            id=order_id,
            symbol=symbol,
            side=side,
            order_type=OrderType(order_type.lower()),
            amount=Decimal(str(amount)),
            price=Decimal(str(price)) if price else None,
            stop_price=Decimal(str(stop_price)) if stop_price else None,
        )

        # 保存到内存缓存
        self._orders[order_id] = order
        logger.info(f"创建订单：{order_id} {side.upper()} {amount} {symbol} @ {order_type}")

        return order

    async def submit_order(self, order: Order) -> bool:
        """
        提交订单到交易所

        Args:
            order: 订单对象

        Returns:
            是否提交成功
        """
        if not self.exchange_manager:
            logger.error("交易所管理器未设置")
            return False

        try:
            # 根据订单类型调用不同的下单方法
            if order.order_type == OrderType.MARKET:
                result = await self.exchange_manager.create_market_order(
                    symbol=order.symbol,
                    side=order.side,
                    amount=float(order.amount),
                )
            elif order.order_type == OrderType.LIMIT:
                result = await self.exchange_manager.create_limit_order(
                    symbol=order.symbol,
                    side=order.side,
                    amount=float(order.amount),
                    price=float(order.price),
                )
            elif order.order_type in [OrderType.STOP_MARKET, OrderType.TAKE_PROFIT_MARKET]:
                result = await self.exchange_manager.create_stop_market_order(
                    symbol=order.symbol,
                    side=order.side,
                    amount=float(order.amount),
                    stop_price=float(order.stop_price),
                )
            elif order.order_type in [OrderType.STOP_LIMIT, OrderType.TAKE_PROFIT_LIMIT]:
                result = await self.exchange_manager.create_stop_limit_order(
                    symbol=order.symbol,
                    side=order.side,
                    amount=float(order.amount),
                    price=float(order.price),
                    stop_price=float(order.stop_price),
                )
            else:
                logger.error(f"未知订单类型：{order.order_type}")
                return False

            # 更新订单状态
            if result:
                order.status = OrderStatus.OPEN
                order.exchange_order_id = result.get("id")
                order.updated_at = datetime.now()
                logger.info(f"订单已提交：{order.id} -> {order.exchange_order_id}")

                # 保存到数据库
                await self._save_to_db(order)

            return result is not None

        except Exception as e:
            order.status = OrderStatus.REJECTED
            order.updated_at = datetime.now()
            logger.error(f"提交订单失败：{e}")
            return False

    async def cancel_order(self, order_id: str) -> bool:
        """
        取消订单

        Args:
            order_id: 订单 ID

        Returns:
            是否取消成功
        """
        order = self._orders.get(order_id)
        if not order:
            logger.error(f"订单不存在：{order_id}")
            return False

        if not order.is_active():
            logger.warning(f"订单已成交或已取消，无法撤销：{order_id}")
            return False

        if not self.exchange_manager:
            logger.error("交易所管理器未设置")
            return False

        try:
            if order.exchange_order_id:
                success = await self.exchange_manager.cancel_order(
                    symbol=order.symbol,
                    order_id=order.exchange_order_id,
                )
                if success:
                    order.status = OrderStatus.CANCELLED
                    order.updated_at = datetime.now()
                    logger.info(f"订单已取消：{order_id}")
                    return True
            return False
        except Exception as e:
            logger.error(f"取消订单失败：{e}")
            return False

    async def update_order_status(self, order_id: str, status: OrderStatus, filled: Optional[float] = None):
        """
        更新订单状态

        Args:
            order_id: 订单 ID
            status: 新状态
            filled: 已成交数量
        """
        order = self._orders.get(order_id)
        if not order:
            return

        order.status = status
        order.updated_at = datetime.now()

        if filled is not None:
            order.filled = Decimal(str(filled))
            order.remaining = order.amount - order.filled

            if order.filled > 0 and order.filled < order.amount:
                order.status = OrderStatus.PARTIALLY_FILLED
            elif order.filled >= order.amount:
                order.status = OrderStatus.FILLED

        await self._save_to_db(order)

    def get_order(self, order_id: str) -> Optional[Order]:
        """获取订单"""
        return self._orders.get(order_id)

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """获取所有活动订单"""
        orders = [o for o in self._orders.values() if o.is_active()]
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        return orders

    def get_order_history(self, symbol: Optional[str] = None, limit: int = 50) -> List[Order]:
        """获取订单历史"""
        orders = list(self._orders.values())
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        # 按创建时间倒序
        orders.sort(key=lambda x: x.created_at, reverse=True)
        return orders[:limit]

    async def _save_to_db(self, order: Order):
        """保存到数据库"""
        if not self.db_manager:
            return

        try:
            from src.data.repository import OrderRepository

            async with self.db_manager.get_session() as session:
                repo = OrderRepository(session)
                await repo.create(
                    order_id=order.id,
                    symbol=order.symbol,
                    side=order.side,
                    quantity=float(order.amount),
                    price=float(order.price or 0),
                    status=order.status.value,
                )
        except Exception as e:
            logger.error(f"保存订单到数据库失败：{e}")
