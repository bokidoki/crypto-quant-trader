"""
数据访问层模块
- OrderRepository: 订单 CRUD
- KLineRepository: K 线数据 CRUD
- TradeRepository: 交易记录 CRUD
- PositionRepository: 持仓记录 CRUD
- StrategyRepository: 策略状态 CRUD
"""
import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    OrderModel,
    KLineModel,
    TradeModel,
    PositionModel,
    StrategyModel,
)


class BaseRepository:
    """基础 Repository 类"""

    def __init__(self, session: AsyncSession):
        self.session = session


class OrderRepository(BaseRepository):
    """订单数据访问层"""

    async def create(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        status: str = "pending",
    ) -> OrderModel:
        """创建订单记录"""
        order = OrderModel(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            status=status,
        )
        self.session.add(order)
        await self.session.flush()
        return order

    async def get_by_id(self, order_id: str) -> Optional[OrderModel]:
        """根据订单 ID 获取订单"""
        result = await self.session.execute(
            select(OrderModel).where(OrderModel.order_id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_by_symbol(self, symbol: str) -> List[OrderModel]:
        """根据交易对获取订单列表"""
        result = await self.session.execute(
            select(OrderModel).where(OrderModel.symbol == symbol)
        )
        return list(result.scalars().all())

    async def get_by_status(self, status: str) -> List[OrderModel]:
        """根据状态获取订单列表"""
        result = await self.session.execute(
            select(OrderModel).where(OrderModel.status == status)
        )
        return list(result.scalars().all())

    async def update_status(self, order_id: str, status: str) -> bool:
        """更新订单状态"""
        await self.session.execute(
            update(OrderModel)
            .where(OrderModel.order_id == order_id)
            .values(status=status, updated_at=datetime.utcnow())
        )
        return True

    async def delete(self, order_id: str) -> bool:
        """删除订单"""
        await self.session.execute(
            delete(OrderModel).where(OrderModel.order_id == order_id)
        )
        return True

    async def list_all(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> List[OrderModel]:
        """获取订单列表（分页）"""
        result = await self.session.execute(
            select(OrderModel)
            .order_by(OrderModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())


class KLineRepository(BaseRepository):
    """K 线数据访问层"""

    async def create(
        self,
        symbol: str,
        interval: str,
        open_time: datetime,
        open_price: Decimal,
        high_price: Decimal,
        low_price: Decimal,
        close_price: Decimal,
        volume: Decimal,
    ) -> KLineModel:
        """创建 K 线记录"""
        kline = KLineModel(
            symbol=symbol,
            interval=interval,
            open_time=open_time,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=close_price,
            volume=volume,
        )
        self.session.add(kline)
        await self.session.flush()
        return kline

    async def get_by_symbol_interval(
        self,
        symbol: str,
        interval: str,
        limit: int = 100,
    ) -> List[KLineModel]:
        """根据交易对和周期获取 K 线数据"""
        result = await self.session.execute(
            select(KLineModel)
            .where(KLineModel.symbol == symbol)
            .where(KLineModel.interval == interval)
            .order_by(KLineModel.open_time.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_time_range(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[KLineModel]:
        """获取指定时间范围的 K 线数据"""
        result = await self.session.execute(
            select(KLineModel)
            .where(KLineModel.symbol == symbol)
            .where(KLineModel.interval == interval)
            .where(KLineModel.open_time >= start_time)
            .where(KLineModel.open_time <= end_time)
            .order_by(KLineModel.open_time.asc())
        )
        return list(result.scalars().all())

    async def upsert(
        self,
        symbol: str,
        interval: str,
        open_time: datetime,
        open_price: Decimal,
        high_price: Decimal,
        low_price: Decimal,
        close_price: Decimal,
        volume: Decimal,
    ) -> KLineModel:
        """插入或更新 K 线数据"""
        existing = await self.session.execute(
            select(KLineModel)
            .where(KLineModel.symbol == symbol)
            .where(KLineModel.interval == interval)
            .where(KLineModel.open_time == open_time)
        )
        kline = existing.scalar_one_or_none()

        if kline:
            kline.high_price = max(kline.high_price, high_price)
            kline.low_price = min(kline.low_price, low_price)
            kline.close_price = close_price
            kline.volume += volume
        else:
            kline = KLineModel(
                symbol=symbol,
                interval=interval,
                open_time=open_time,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                volume=volume,
            )
            self.session.add(kline)

        await self.session.flush()
        return kline

    async def delete_old(
        self,
        symbol: str,
        interval: str,
        before_time: datetime,
    ) -> int:
        """删除指定时间之前的 K 线数据"""
        result = await self.session.execute(
            delete(KLineModel)
            .where(KLineModel.symbol == symbol)
            .where(KLineModel.interval == interval)
            .where(KLineModel.open_time < before_time)
        )
        return result.rowcount


class TradeRepository(BaseRepository):
    """交易记录访问层"""

    async def create(
        self,
        order_id: str,
        trade_id: str,
        price: Decimal,
        quantity: Decimal,
        fee: Decimal = Decimal(0),
        fee_asset: Optional[str] = None,
    ) -> TradeModel:
        """创建交易记录"""
        trade = TradeModel(
            order_id=order_id,
            trade_id=trade_id,
            price=price,
            quantity=quantity,
            fee=fee,
            fee_asset=fee_asset,
        )
        self.session.add(trade)
        await self.session.flush()
        return trade

    async def get_by_order_id(self, order_id: str) -> List[TradeModel]:
        """根据订单 ID 获取交易记录"""
        result = await self.session.execute(
            select(TradeModel).where(TradeModel.order_id == order_id)
        )
        return list(result.scalars().all())

    async def get_by_trade_id(self, trade_id: str) -> Optional[TradeModel]:
        """根据成交 ID 获取交易记录"""
        result = await self.session.execute(
            select(TradeModel).where(TradeModel.trade_id == trade_id)
        )
        return result.scalar_one_or_none()

    async def list_by_symbol(
        self,
        symbol: str,
        limit: int = 100,
    ) -> List[TradeModel]:
        """根据交易对获取交易记录列表"""
        # 需要通过 order_id 关联查询
        result = await self.session.execute(
            select(TradeModel)
            .join(OrderModel, TradeModel.order_id == OrderModel.order_id)
            .where(OrderModel.symbol == symbol)
            .order_by(TradeModel.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def delete(self, trade_id: str) -> bool:
        """删除交易记录"""
        await self.session.execute(
            delete(TradeModel).where(TradeModel.trade_id == trade_id)
        )
        return True


class PositionRepository(BaseRepository):
    """持仓记录访问层"""

    async def upsert(
        self,
        symbol: str,
        quantity: Decimal,
        entry_price: Decimal,
        current_price: Decimal,
        unrealized_pnl: Decimal = Decimal(0),
        realized_pnl: Decimal = Decimal(0),
    ) -> PositionModel:
        """插入或更新持仓记录"""
        existing = await self.session.execute(
            select(PositionModel).where(PositionModel.symbol == symbol)
        )
        position = existing.scalar_one_or_none()

        if position:
            position.quantity = quantity
            position.entry_price = entry_price
            position.current_price = current_price
            position.unrealized_pnl = unrealized_pnl
            position.realized_pnl = realized_pnl
        else:
            position = PositionModel(
                symbol=symbol,
                quantity=quantity,
                entry_price=entry_price,
                current_price=current_price,
                unrealized_pnl=unrealized_pnl,
                realized_pnl=realized_pnl,
            )
            self.session.add(position)

        await self.session.flush()
        return position

    async def get_by_symbol(self, symbol: str) -> Optional[PositionModel]:
        """根据交易对获取持仓"""
        result = await self.session.execute(
            select(PositionModel).where(PositionModel.symbol == symbol)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> List[PositionModel]:
        """获取所有持仓"""
        result = await self.session.execute(select(PositionModel))
        return list(result.scalars().all())

    async def update_price(
        self,
        symbol: str,
        current_price: Decimal,
    ) -> bool:
        """更新当前价格"""
        await self.session.execute(
            update(PositionModel)
            .where(PositionModel.symbol == symbol)
            .values(
                current_price=current_price,
                updated_at=datetime.utcnow(),
            )
        )
        return True

    async def delete(self, symbol: str) -> bool:
        """删除持仓记录"""
        await self.session.execute(
            delete(PositionModel).where(PositionModel.symbol == symbol)
        )
        return True


class StrategyRepository(BaseRepository):
    """策略状态访问层"""

    async def upsert(
        self,
        name: str,
        parameters: Optional[Dict[str, Any]] = None,
        stats: Optional[Dict[str, Any]] = None,
        is_active: bool = True,
    ) -> StrategyModel:
        """插入或更新策略状态"""
        existing = await self.session.execute(
            select(StrategyModel).where(StrategyModel.name == name)
        )
        strategy = existing.scalar_one_or_none()

        if strategy:
            strategy.parameters = json.dumps(parameters) if parameters else strategy.parameters
            strategy.stats = json.dumps(stats) if stats else strategy.stats
            strategy.is_active = is_active
        else:
            strategy = StrategyModel(
                name=name,
                parameters=json.dumps(parameters) if parameters else None,
                stats=json.dumps(stats) if stats else None,
                is_active=is_active,
            )
            self.session.add(strategy)

        await self.session.flush()
        return strategy

    async def get_by_name(self, name: str) -> Optional[StrategyModel]:
        """根据策略名获取策略状态"""
        result = await self.session.execute(
            select(StrategyModel).where(StrategyModel.name == name)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> List[StrategyModel]:
        """获取所有策略"""
        result = await self.session.execute(select(StrategyModel))
        return list(result.scalars().all())

    async def get_active(self) -> List[StrategyModel]:
        """获取所有激活的策略"""
        result = await self.session.execute(
            select(StrategyModel).where(StrategyModel.is_active == True)
        )
        return list(result.scalars().all())

    async def update_stats(
        self,
        name: str,
        stats: Dict[str, Any],
    ) -> bool:
        """更新策略统计数据"""
        await self.session.execute(
            update(StrategyModel)
            .where(StrategyModel.name == name)
            .values(
                stats=json.dumps(stats),
                updated_at=datetime.utcnow(),
            )
        )
        return True

    async def set_active(self, name: str, is_active: bool) -> bool:
        """设置策略激活状态"""
        await self.session.execute(
            update(StrategyModel)
            .where(StrategyModel.name == name)
            .values(
                is_active=is_active,
                updated_at=datetime.utcnow(),
            )
        )
        return True

    async def delete(self, name: str) -> bool:
        """删除策略记录"""
        await self.session.execute(
            delete(StrategyModel).where(StrategyModel.name == name)
        )
        return True
