"""
交易所基类
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass
from datetime import datetime


class OrderSide(Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """订单类型"""
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    STOP_LOSS_LIMIT = "stop_loss_limit"
    TAKE_PROFIT = "take_profit"
    TAKE_PROFIT_LIMIT = "take_profit_limit"


class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REJECTED = "rejected"


@dataclass
class Order:
    """订单"""
    id: str
    symbol: str
    side: OrderSide
    type: OrderType
    amount: float
    price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled: float = 0.0
    remaining: float = 0.0
    cost: float = 0.0
    fee: float = 0.0
    timestamp: datetime = None
    info: Dict = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.remaining == 0:
            self.remaining = self.amount


@dataclass
class Position:
    """持仓"""
    symbol: str
    side: OrderSide
    amount: float
    entry_price: float
    current_price: float
    unrealized_pnl: float = 0.0
    percentage: float = 0.0
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        self.update_pnl()
    
    def update_pnl(self):
        """更新盈亏"""
        if self.side == OrderSide.BUY:
            self.unrealized_pnl = (self.current_price - self.entry_price) * self.amount
        else:
            self.unrealized_pnl = (self.entry_price - self.current_price) * self.amount
        
        if self.entry_price > 0:
            self.percentage = (self.unrealized_pnl / (self.entry_price * self.amount)) * 100


@dataclass
class Ticker:
    """行情"""
    symbol: str
    last: float
    bid: float
    ask: float
    high: float
    low: float
    volume: float
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class KLine:
    """K线"""
    symbol: str
    interval: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class BaseExchange(ABC):
    """
    交易所基类
    
    所有交易所实现必须继承此类并实现所有抽象方法。
    """
    
    def __init__(self, name: str):
        self.name = name
        self.connected = False
    
    @abstractmethod
    async def connect(self):
        """连接交易所"""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """断开连接"""
        pass
    
    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker:
        """获取行情"""
        pass
    
    @abstractmethod
    async def get_klines(self, symbol: str, interval: str, limit: int = 100) -> List[KLine]:
        """获取K线"""
        pass
    
    @abstractmethod
    async def get_balance(self) -> Dict[str, float]:
        """获取账户余额"""
        pass
    
    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """获取持仓"""
        pass
    
    @abstractmethod
    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: float,
        price: Optional[float] = None,
    ) -> Order:
        """创建订单"""
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        pass
    
    @abstractmethod
    async def get_order(self, order_id: str, symbol: str) -> Order:
        """获取订单"""
        pass
    
    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """获取未完成订单"""
        pass
    
    @abstractmethod
    async def subscribe_ticker(self, symbol: str, callback):
        """订阅行情"""
        pass
    
    @abstractmethod
    async def subscribe_klines(self, symbol: str, interval: str, callback):
        """订阅K线"""
        pass
