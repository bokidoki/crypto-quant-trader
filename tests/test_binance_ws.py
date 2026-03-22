"""
Binance WebSocket 测试
"""
import asyncio
from datetime import datetime
from loguru import logger
import sys

sys.path.insert(0, '.')

from src.exchanges.binance import BinanceExchange


async def on_ticker(ticker):
    """行情回调"""
    logger.info(f"[Ticker] {ticker.symbol}: ${ticker.last} (vol: {ticker.volume:.2f})")


async def on_kline(kline):
    """K 线回调"""
    status = "closed" if kline.is_closed else "open"
    logger.info(
        f"[KLine {kline.interval}] {kline.symbol}: "
        f"O:{kline.open} H:{kline.high} L:{kline.low} C:{kline.close} [{status}]"
    )


async def test_binance_websocket():
    """测试 Binance WebSocket 行情订阅"""
    logger.add("logs/test_binance_ws.log", rotation="10 MB", retention="1 day")

    exchange = BinanceExchange()

    try:
        # 连接（仅初始化，不需要 API key 用于公共数据）
        await exchange.connect()
        logger.info("Binance 已连接")

        # 订阅 BTC/USDT 行情
        logger.info("订阅 BTC/USDT 行情...")
        await exchange.subscribe_ticker("BTC/USDT", on_ticker)

        # 订阅 ETH/USDT 1 分钟 K 线
        logger.info("订阅 ETH/USDT 1 分钟 K 线...")
        await exchange.subscribe_klines("ETH/USDT", "1m", on_kline)

        # 订阅 BTC/USDT 5 分钟 K 线
        logger.info("订阅 BTC/USDT 5 分钟 K 线...")
        await exchange.subscribe_klines("BTC/USDT", "5m", on_kline)

        # 等待数据
        logger.info("等待 WebSocket 数据... (30 秒)")
        await asyncio.sleep(30)

        # 取消订阅
        logger.info("取消订阅...")
        await exchange.unsubscribe_klines("ETH/USDT", "1m")
        await asyncio.sleep(5)

        # 继续运行一段时间
        logger.info("继续接收数据... (10 秒)")
        await asyncio.sleep(10)

    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.error(f"错误：{e}")
    finally:
        await exchange.disconnect()
        logger.info("测试结束")


if __name__ == "__main__":
    asyncio.run(test_binance_websocket())
