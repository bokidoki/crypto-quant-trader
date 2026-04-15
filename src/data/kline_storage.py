"""
K 线存储模块
- 支持多周期 K 线数据存储
- 支持查询和聚合
"""
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .models import KLineModel
from .database import get_db_manager


class KLineStorage:
    """
    K 线数据存储器

    功能:
    - 存储 K 线数据到 SQLite
    - 查询指定交易对和周期的 K 线
    - 查询时间范围数据
    - 数据去重（upsert）
    """

    # 支持的周期列表
    SUPPORTED_INTERVALS = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"]

    def __init__(self, db_manager=None):
        self.db_manager = db_manager or get_db_manager()

    async def store(
        self,
        symbol: str,
        interval: str,
        open_time: datetime,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        quote_volume: float = 0.0,
        trades_count: int = 0,
    ) -> bool:
        """
        存储单根 K 线

        Args:
            symbol: 交易对
            interval: 周期
            open_time: 开盘时间
            open: 开盘价
            high: 最高价
            low: 最低价
            close: 收盘价
            volume: 成交量
            quote_volume: 成交额
            trades_count: 成交笔数
        """
        try:
            async with self.db_manager.get_session() as session:
                # 检查是否已存在
                result = await session.execute(
                    select(KLineModel).where(
                        KLineModel.symbol == symbol,
                        KLineModel.interval == interval,
                        KLineModel.open_time == open_time,
                    )
                )
                existing = result.scalar_one_or_none()

                if existing:
                    # 更新 K 线（取最高价、最低价，更新收盘价和成交量）
                    existing.high_price = max(existing.high_price, Decimal(str(high)))
                    existing.low_price = min(existing.low_price, Decimal(str(low)))
                    existing.close_price = Decimal(str(close))
                    existing.volume += Decimal(str(volume))
                    existing.quote_volume = Decimal(str(quote_volume))
                    existing.trades_count += trades_count
                else:
                    # 插入新 K 线
                    kline = KLineModel(
                        symbol=symbol,
                        interval=interval,
                        open_time=open_time,
                        open_price=Decimal(str(open)),
                        high_price=Decimal(str(high)),
                        low_price=Decimal(str(low)),
                        close_price=Decimal(str(close)),
                        volume=Decimal(str(volume)),
                        quote_volume=Decimal(str(quote_volume)),
                        trades_count=trades_count,
                    )
                    session.add(kline)

                await session.commit()
                return True

        except Exception as e:
            from loguru import logger
            logger.error(f"存储 K 线失败：{e}")
            return False

    async def store_batch(
        self,
        symbol: str,
        interval: str,
        klines: List[Dict],
    ) -> int:
        """
        批量存储 K 线

        Args:
            symbol: 交易对
            interval: 周期
            klines: K 线列表，每项包含 {open_time, open, high, low, close, volume}

        Returns:
            成功存储的数量
        """
        count = 0
        for kline in klines:
            success = await self.store(
                symbol=symbol,
                interval=interval,
                open_time=kline["open_time"],
                open=kline["open"],
                high=kline["high"],
                low=kline["low"],
                close=kline["close"],
                volume=kline["volume"],
                quote_volume=kline.get("quote_volume", 0.0),
                trades_count=kline.get("trades_count", 0),
            )
            if success:
                count += 1
        return count

    async def get_latest(
        self,
        symbol: str,
        interval: str,
        limit: int = 100,
    ) -> List[KLineModel]:
        """
        获取最新的 K 线数据

        Args:
            symbol: 交易对
            interval: 周期
            limit: 数量限制

        Returns:
            K 线列表（按时间倒序）
        """
        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    select(KLineModel)
                    .where(KLineModel.symbol == symbol)
                    .where(KLineModel.interval == interval)
                    .order_by(KLineModel.open_time.desc())
                    .limit(limit)
                )
                return list(result.scalars().all())
        except Exception as e:
            from loguru import logger
            logger.error(f"获取 K 线失败：{e}")
            return []

    async def get_by_time_range(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[KLineModel]:
        """
        获取指定时间范围的 K 线数据

        Args:
            symbol: 交易对
            interval: 周期
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            K 线列表（按时间正序）
        """
        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    select(KLineModel)
                    .where(KLineModel.symbol == symbol)
                    .where(KLineModel.interval == interval)
                    .where(KLineModel.open_time >= start_time)
                    .where(KLineModel.open_time <= end_time)
                    .order_by(KLineModel.open_time.asc())
                )
                return list(result.scalars().all())
        except Exception as e:
            from loguru import logger
            logger.error(f"获取 K 线失败：{e}")
            return []

    async def get_symbols(self) -> List[str]:
        """获取所有有数据的交易对"""
        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    select(KLineModel.symbol).distinct()
                )
                return [row[0] for row in result.all()]
        except Exception as e:
            from loguru import logger
            logger.error(f"获取交易对失败：{e}")
            return []

    async def delete_old(
        self,
        symbol: str,
        interval: str,
        before_time: datetime,
    ) -> int:
        """
        删除指定时间之前的 K 线数据

        Args:
            symbol: 交易对
            interval: 周期
            before_time: 删除此时间之前的数据

        Returns:
            删除的记录数
        """
        try:
            async with self.db_manager.get_session() as session:
                from sqlalchemy import delete
                result = await session.execute(
                    delete(KLineModel)
                    .where(KLineModel.symbol == symbol)
                    .where(KLineModel.interval == interval)
                    .where(KLineModel.open_time < before_time)
                )
                await session.commit()
                return result.rowcount
        except Exception as e:
            from loguru import logger
            logger.error(f"删除 K 线失败：{e}")
            return 0


# 全局存储实例
_kline_storage: Optional[KLineStorage] = None


def get_kline_storage() -> KLineStorage:
    """获取全局 K 线存储实例"""
    global _kline_storage
    if _kline_storage is None:
        _kline_storage = KLineStorage()
    return _kline_storage
