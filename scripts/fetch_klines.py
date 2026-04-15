"""
手动获取 K 线数据脚本
用于初始化历史 K 线数据
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
import random

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import ccxt
from src.data.kline_storage import get_kline_storage
from src.core.config import get_settings


async def fetch_initial_klines():
    """获取初始 K 线数据（使用模拟数据）"""
    from src.data.database import get_db_manager
    from src.data.models import Base
    settings = get_settings()

    # 先创建数据库表
    print("创建数据库表...")
    db_manager = get_db_manager()
    async with db_manager.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("数据库表创建完成")

    storage = get_kline_storage()

    # 采集配置
    symbols = ["BTC/USDT", "ETH/USDT"]  # 默认采集的交易对
    intervals = ["1m", "5m", "15m", "1h", "4h", "1d"]  # 采集周期

    # 基础价格
    base_prices = {
        "BTC/USDT": 68000,
        "ETH/USDT": 3500,
    }

    print(f"开始生成模拟 K 线数据...")
    print(f"交易对：{symbols}")
    print(f"周期：{intervals}")

    total_count = 0

    for symbol in symbols:
        base_price = base_prices.get(symbol, 100)

        for interval in intervals:
            try:
                print(f"\n生成 {symbol} {interval}...")

                # 根据周期确定 K 线数量和时间间隔
                if interval == "1m":
                    klines_count = 500
                    minutes_per_kline = 1
                elif interval == "5m":
                    klines_count = 500
                    minutes_per_kline = 5
                elif interval == "15m":
                    klines_count = 500
                    minutes_per_kline = 15
                elif interval == "1h":
                    klines_count = 500
                    minutes_per_kline = 60
                elif interval == "4h":
                    klines_count = 500
                    minutes_per_kline = 240
                elif interval == "1d":
                    klines_count = 365
                    minutes_per_kline = 1440
                else:
                    klines_count = 500
                    minutes_per_kline = 60

                # 生成模拟 K 线
                klines = []
                # 从现在往回推算
                end_time = datetime.now().replace(second=0, microsecond=0)
                current_time = end_time - timedelta(minutes=minutes_per_kline * klines_count)
                current_price = base_price

                for i in range(klines_count):
                    # 随机波动 (±2%)
                    change = random.uniform(-0.02, 0.02)
                    open_price = current_price
                    close_price = current_price * (1 + change)
                    high_price = max(open_price, close_price) * (1 + random.uniform(0, 0.01))
                    low_price = min(open_price, close_price) * (1 - random.uniform(0, 0.01))
                    volume = random.uniform(10, 100)

                    klines.append({
                        "open_time": current_time,
                        "open": round(open_price, 2),
                        "high": round(high_price, 2),
                        "low": round(low_price, 2),
                        "close": round(close_price, 2),
                        "volume": round(volume, 4),
                        "quote_volume": round(volume * current_price, 2),
                        "trades_count": random.randint(100, 1000),
                    })

                    current_price = close_price
                    current_time += timedelta(minutes=minutes_per_kline)

                # 存储到数据库
                count = await storage.store_batch(symbol, interval, klines)
                print(f"  存储成功：{count}/{len(klines)} 根 K 线")
                total_count += count

            except Exception as e:
                print(f"  生成失败：{e}")

    print(f"\n生成完成！共存储 {total_count} 根 K 线")

    # 添加交易对到关注列表
    from src.data.models import SymbolWatchModel
    from src.data.database import get_db_session
    from sqlalchemy import select

    async with get_db_session() as db:
        for symbol in symbols:
            # 检查是否已存在
            result = await db.execute(
                select(SymbolWatchModel).where(
                    SymbolWatchModel.symbol == symbol,
                    SymbolWatchModel.exchange == "binance"
                )
            )
            existing = result.scalar_one_or_none()

            if not existing:
                db.add(SymbolWatchModel(
                    exchange="binance",
                    symbol=symbol,
                    name=symbol
                ))
                print(f"已添加关注交易对：{symbol}")

        await db.commit()

    print("\n完成！请刷新 Web 页面查看 K 线图表")


if __name__ == "__main__":
    asyncio.run(fetch_initial_klines())
