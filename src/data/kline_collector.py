"""
K 线采集器模块
- 从交易所获取 K 线数据
- 支持多周期自动采集
- 定时任务调度
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from loguru import logger


class KLineCollector:
    """
    K 线采集器

    功能:
    - 从交易所获取 K 线数据
    - 支持多交易对、多周期采集
    - 自动补全历史数据
    - 实时采集最新 K 线
    """

    # 默认采集周期
    DEFAULT_INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d"]

    # ccxt 周期映射
    TIMEFRAME_MAP = {
        "1m": "1m",
        "3m": "3m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "6h": "6h",
        "12h": "12h",
        "1d": "1d",
        "1w": "1w",
    }

    def __init__(self, exchange: Any, storage: Any = None):
        """
        初始化采集器

        Args:
            exchange: 交易所实例（ccxt 异步客户端）
            storage: KLineStorage 实例
        """
        self.exchange = exchange
        self.storage = storage
        self.running = False
        self.tasks: Dict[str, asyncio.Task] = {}

        # 采集配置
        self.symbols: List[str] = []  # 要采集的交易对列表
        self.intervals: List[str] = []  # 要采集的周期列表

    def configure(self, symbols: List[str], intervals: List[str] = None):
        """
        配置采集参数

        Args:
            symbols: 交易对列表，如 ["BTC/USDT", "ETH/USDT"]
            intervals: 周期列表，如 ["1m", "5m", "1h"]
        """
        self.symbols = symbols
        self.intervals = intervals or self.DEFAULT_INTERVALS.copy()
        logger.info(f"K 线采集器配置：{len(self.symbols)} 个交易对，{len(self.intervals)} 个周期")

    async def start(self):
        """启动采集器"""
        if self.running:
            logger.warning("K 线采集器已在运行")
            return

        self.running = True
        logger.info("K 线采集器启动")

        # 为每个交易对和周期创建采集任务
        for symbol in self.symbols:
            for interval in self.intervals:
                task_key = f"{symbol}_{interval}"
                task = asyncio.create_task(self._collect_loop(symbol, interval))
                self.tasks[task_key] = task
                logger.info(f"采集任务已创建：{task_key}")

    async def stop(self):
        """停止采集器"""
        if not self.running:
            return

        self.running = False
        logger.info("K 线采集器停止中...")

        # 取消所有采集任务
        for task_key, task in self.tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info(f"采集任务已停止：{task_key}")

        self.tasks.clear()
        logger.info("K 线采集器已停止")

    async def _collect_loop(self, symbol: str, interval: str):
        """
        单个交易对和周期的采集循环

        Args:
            symbol: 交易对
            interval: 周期
        """
        logger.info(f"开始采集：{symbol} {interval}")

        # 首次采集：获取最近 100 根 K 线
        await self._fetch_and_store(symbol, interval, limit=100)

        # 定时采集：每分钟采集最新 K 线
        while self.running:
            try:
                # 等待 K 线闭合（周期边界）
                await asyncio.sleep(60)  # 每分钟检查一次

                # 采集最新 K 线
                await self._fetch_and_store(symbol, interval, limit=5)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"采集失败 {symbol} {interval}: {e}")
                await asyncio.sleep(5)  # 错误后等待 5 秒

    async def _fetch_and_store(
        self,
        symbol: str,
        interval: str,
        limit: int = 100,
    ):
        """
        获取 K 线并存储

        Args:
            symbol: 交易对
            interval: 周期
            limit: 获取数量
        """
        try:
            # 从交易所获取 K 线
            timeframe = self.TIMEFRAME_MAP.get(interval, interval)
            klines_data = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

            if not klines_data:
                logger.warning(f"获取 K 线为空：{symbol} {interval}")
                return

            # 转换为统一格式
            klines = []
            for k in klines_data:
                kline = {
                    "open_time": datetime.fromtimestamp(k[0] / 1000),
                    "open": k[1],
                    "high": k[2],
                    "low": k[3],
                    "close": k[4],
                    "volume": k[5],
                    "quote_volume": k[6] if len(k) > 6 else 0.0,
                    "trades_count": 0,
                }
                klines.append(kline)

            # 存储到数据库
            if self.storage:
                count = await self.storage.store_batch(symbol, interval, klines)
                logger.debug(f"存储 K 线 {symbol} {interval}: {count}/{len(klines)}")
            else:
                logger.warning("KLineStorage 未设置，无法存储")

        except Exception as e:
            logger.error(f"获取并存储 K 线失败 {symbol} {interval}: {e}")
            raise

    async def fetch_historical(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> int:
        """
        获取历史 K 线数据

        Args:
            symbol: 交易对
            interval: 周期
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            获取的 K 线数量
        """
        logger.info(f"获取历史 K 线：{symbol} {interval} {start_time} -> {end_time}")

        total_count = 0
        timeframe = self.TIMEFRAME_MAP.get(interval, interval)

        # ccxt 每次最多获取 1000 根 K 线
        current_time = start_time
        while current_time < end_time:
            try:
                klines_data = await self.exchange.fetch_ohlcv(
                    symbol, timeframe,
                    since=int(current_time.timestamp() * 1000),
                    limit=1000
                )

                if not klines_data:
                    break

                # 转换为统一格式
                klines = []
                for k in klines_data:
                    kline_time = datetime.fromtimestamp(k[0] / 1000)
                    if kline_time > end_time:
                        break
                    klines.append({
                        "open_time": kline_time,
                        "open": k[1],
                        "high": k[2],
                        "low": k[3],
                        "close": k[4],
                        "volume": k[5],
                        "quote_volume": k[6] if len(k) > 6 else 0.0,
                        "trades_count": 0,
                    })

                # 存储
                if self.storage and klines:
                    await self.storage.store_batch(symbol, interval, klines)
                    total_count += len(klines)
                    logger.debug(f"历史 K 线已存储：{len(klines)}")

                # 更新当前时间
                if klines:
                    current_time = klines[-1]["open_time"] + timedelta(minutes=1)
                else:
                    break

                # 避免频率限制
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"获取历史 K 线失败：{e}")
                break

        logger.info(f"历史 K 线获取完成：{total_count} 根")
        return total_count


# 全局采集器实例
_collector: Optional[KLineCollector] = None


def get_kline_collector(exchange: Any, storage: Any = None) -> KLineCollector:
    """获取全局 K 线采集器实例"""
    global _collector
    if _collector is None:
        _collector = KLineCollector(exchange, storage)
    return _collector


def reset_collector():
    """重置采集器实例"""
    global _collector
    _collector = None
