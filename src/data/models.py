"""
数据模型模块
- OrderModel: 订单记录
- KLineModel: K 线数据
- TradeModel: 交易记录
- PositionModel: 持仓记录
- StrategyModel: 策略状态
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DECIMAL, String, Text
from sqlalchemy.orm import Mapped, DeclarativeBase, mapped_column


class Base(DeclarativeBase):
    """基础模型类"""
    pass


class OrderModel(Base):
    """订单记录模型"""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, comment="订单 ID")
    symbol: Mapped[str] = mapped_column(String(32), index=True, comment="交易对")
    side: Mapped[str] = mapped_column(String(16), comment="方向：buy/sell")
    quantity: Mapped[Decimal] = mapped_column(DECIMAL(32, 16), comment="数量")
    price: Mapped[Decimal] = mapped_column(DECIMAL(32, 16), comment="价格")
    status: Mapped[str] = mapped_column(String(32), default="pending", comment="状态")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="更新时间"
    )

    def __repr__(self) -> str:
        return f"<Order(order_id={self.order_id}, symbol={self.symbol}, side={self.side})>"


class KLineModel(Base):
    """K 线数据模型"""

    __tablename__ = "klines"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True, comment="交易对")
    interval: Mapped[str] = mapped_column(String(16), index=True, comment="周期")
    open_time: Mapped[datetime] = mapped_column(index=True, comment="开盘时间")
    open_price: Mapped[Decimal] = mapped_column(DECIMAL(32, 16), comment="开盘价")
    high_price: Mapped[Decimal] = mapped_column(DECIMAL(32, 16), comment="最高价")
    low_price: Mapped[Decimal] = mapped_column(DECIMAL(32, 16), comment="最低价")
    close_price: Mapped[Decimal] = mapped_column(DECIMAL(32, 16), comment="收盘价")
    volume: Mapped[Decimal] = mapped_column(DECIMAL(32, 16), comment="成交量")

    def __repr__(self) -> str:
        return f"<KLine(symbol={self.symbol}, interval={self.interval}, open_time={self.open_time})>"


class TradeModel(Base):
    """交易记录模型"""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), index=True, comment="订单 ID")
    trade_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, comment="成交 ID")
    price: Mapped[Decimal] = mapped_column(DECIMAL(32, 16), comment="成交价")
    quantity: Mapped[Decimal] = mapped_column(DECIMAL(32, 16), comment="成交量")
    fee: Mapped[Decimal] = mapped_column(DECIMAL(32, 16), default=Decimal(0), comment="手续费")
    fee_asset: Mapped[Optional[str]] = mapped_column(String(16), comment="手续费币种")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, comment="创建时间")

    def __repr__(self) -> str:
        return f"<Trade(trade_id={self.trade_id}, order_id={self.order_id}, price={self.price})>"


class PositionModel(Base):
    """持仓记录模型"""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="交易对")
    quantity: Mapped[Decimal] = mapped_column(DECIMAL(32, 16), default=Decimal(0), comment="数量")
    entry_price: Mapped[Decimal] = mapped_column(DECIMAL(32, 16), default=Decimal(0), comment="入场价")
    current_price: Mapped[Decimal] = mapped_column(DECIMAL(32, 16), default=Decimal(0), comment="当前价")
    unrealized_pnl: Mapped[Decimal] = mapped_column(DECIMAL(32, 16), default=Decimal(0), comment="未实现盈亏")
    realized_pnl: Mapped[Decimal] = mapped_column(DECIMAL(32, 16), default=Decimal(0), comment="已实现盈亏")
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="更新时间"
    )

    def __repr__(self) -> str:
        return f"<Position(symbol={self.symbol}, quantity={self.quantity}, entry_price={self.entry_price})>"


class StrategyModel(Base):
    """策略状态模型"""

    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True, comment="策略名")
    parameters: Mapped[Optional[str]] = mapped_column(Text, comment="参数 (JSON)")
    stats: Mapped[Optional[str]] = mapped_column(Text, comment="统计数据 (JSON)")
    is_active: Mapped[bool] = mapped_column(default=True, comment="是否激活")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="更新时间"
    )

    def __repr__(self) -> str:
        return f"<Strategy(name={self.name}, is_active={self.is_active})>"
