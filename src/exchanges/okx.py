"""
OKX 交易所接口
"""
import asyncio
import json
import time
from typing import Dict, List, Optional, Callable
from datetime import datetime
import zlib
import base64

import ccxt.async_support as ccxt
from loguru import logger
import websockets

from .base import (
    BaseExchange, Order, OrderSide, OrderType, OrderStatus,
    Position, Ticker, KLine
)
from ..core.config import get_settings


class OKXExchange(BaseExchange):
    """
    OKX 交易所实现

    支持现货交易，使用 ccxt 库。
    """

    def __init__(self):
        super().__init__("okx")
        self.settings = get_settings()
        self.client: Optional[ccxt.okx] = None
        # WebSocket 相关
        self.ws_url = "wss://ws.okx.com:8443/ws/v5/public"
        self.ws_tasks: Dict[str, asyncio.Task] = {}  # 订阅任务
        self.ticker_callbacks: Dict[str, List[Callable]] = {}  # 行情回调
        self.kline_callbacks: Dict[str, Dict[str, List[Callable]]] = {}  # K 线回调

    async def connect(self):
        """连接 OKX"""
        config = self.settings.okx

        if not config.enabled:
            logger.info("OKX 未启用")
            return

        self.client = ccxt.okx(
            {
                "apiKey": config.api_key,
                "secret": config.api_secret,
                "password": config.passphrase,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "spot",
                },
            }
        )

        # 模拟盘设置
        if config.simulated:
            self.client.set_sandbox_mode(True)
            logger.info("OKX 模拟盘模式")

        # 代理设置 (ccxt 异步版本使用 aiohttp_proxy)
        if self.settings.proxy.enabled:
            self.client.aiohttp_proxy = self.settings.proxy.http
            logger.info(f"OKX 使用代理：{self.settings.proxy.http}")

        # 加载市场
        await self.client.load_markets()

        self.connected = True
        logger.info(f"OKX 已连接，市场数：{len(self.client.markets)}")

    async def disconnect(self):
        """断开连接"""
        # 取消所有 WebSocket 订阅
        for task in self.ws_tasks.values():
            task.cancel()
        self.ws_tasks.clear()
        self.ticker_callbacks.clear()
        self.kline_callbacks.clear()

        if self.client:
            await self.client.close()
            self.connected = False
            logger.info("OKX 已断开")

    async def get_ticker(self, symbol: str) -> Ticker:
        """获取行情"""
        if not self.connected:
            raise RuntimeError("OKX 未连接")

        ticker = await self.client.fetch_ticker(symbol)

        return Ticker(
            symbol=symbol,
            last=ticker["last"],
            bid=ticker["bid"],
            ask=ticker["ask"],
            high=ticker["high"],
            low=ticker["low"],
            volume=ticker["baseVolume"],
            timestamp=datetime.fromtimestamp(ticker["timestamp"] / 1000),
        )

    async def get_klines(
        self, symbol: str, interval: str = "1h", limit: int = 100
    ) -> List[KLine]:
        """获取 K 线"""
        if not self.connected:
            raise RuntimeError("OKX 未连接")

        ohlcv = await self.client.fetch_ohlcv(symbol, interval, limit=limit)

        klines = []
        for candle in ohlcv:
            klines.append(
                KLine(
                    symbol=symbol,
                    interval=interval,
                    timestamp=datetime.fromtimestamp(candle[0] / 1000),
                    open=candle[1],
                    high=candle[2],
                    low=candle[3],
                    close=candle[4],
                    volume=candle[5],
                )
            )

        return klines

    async def get_balance(self) -> Dict[str, float]:
        """获取账户余额"""
        if not self.connected:
            raise RuntimeError("OKX 未连接")

        balance = await self.client.fetch_balance()

        # 只返回非零余额
        result = {}
        for currency, amount in balance.items():
            if isinstance(amount, dict):
                total = amount.get("total", 0)
                if total > 0:
                    result[currency] = total

        return result

    async def get_positions(self) -> List[Position]:
        """获取持仓"""
        if not self.connected:
            raise RuntimeError("OKX 未连接")

        # 现货无持仓概念
        return []

    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: float,
        price: Optional[float] = None,
    ) -> Order:
        """创建订单"""
        if not self.connected:
            raise RuntimeError("OKX 未连接")

        type_map = {
            OrderType.MARKET: "market",
            OrderType.LIMIT: "limit",
            OrderType.STOP_LOSS: "market",
            OrderType.TAKE_PROFIT: "market",
        }

        params = {}
        if order_type in [OrderType.STOP_LOSS, OrderType.TAKE_PROFIT]:
            if price is None:
                raise ValueError(f"{order_type.value} 需要提供触发价格")
            params["stopLossPrice" if order_type == OrderType.STOP_LOSS else "takeProfitPrice"] = price

        order = await self.client.create_order(
            symbol=symbol,
            type=type_map.get(order_type, "market"),
            side=side.value,
            amount=amount,
            price=price if order_type == OrderType.LIMIT else None,
            params=params if params else None,
        )

        logger.info(f"订单已创建：{order['id']} {side.value} {amount} {symbol}")

        return self._parse_order(order)

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        if not self.connected:
            raise RuntimeError("OKX 未连接")

        try:
            await self.client.cancel_order(order_id, symbol)
            logger.info(f"订单已取消：{order_id}")
            return True
        except Exception as e:
            logger.error(f"取消订单失败：{order_id}, 错误：{e}")
            return False

    async def get_order(self, order_id: str, symbol: str) -> Order:
        """获取订单"""
        if not self.connected:
            raise RuntimeError("OKX 未连接")

        order = await self.client.fetch_order(order_id, symbol)
        return self._parse_order(order)

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """获取未完成订单"""
        if not self.connected:
            raise RuntimeError("OKX 未连接")

        orders = await self.client.fetch_open_orders(symbol)
        return [self._parse_order(o) for o in orders]

    async def subscribe_ticker(self, symbol: str, callback: Callable):
        """订阅行情"""
        if symbol not in self.ticker_callbacks:
            self.ticker_callbacks[symbol] = []
        self.ticker_callbacks[symbol].append(callback)

        # 如果尚未订阅，启动 WebSocket 连接
        if symbol not in self.ws_tasks:
            self.ws_tasks[symbol] = asyncio.create_task(
                self._ws_ticker_loop(symbol)
            )
            logger.info(f"OKX WebSocket 行情订阅：{symbol}")

    async def subscribe_klines(self, symbol: str, interval: str, callback: Callable):
        """订阅 K 线"""
        if symbol not in self.kline_callbacks:
            self.kline_callbacks[symbol] = {}
        if interval not in self.kline_callbacks[symbol]:
            self.kline_callbacks[symbol][interval] = []
        self.kline_callbacks[symbol][interval].append(callback)

        # 如果尚未订阅，启动 WebSocket 连接
        if symbol not in self.ws_tasks:
            self.ws_tasks[symbol] = asyncio.create_task(
                self._ws_kline_loop(symbol, interval)
            )
            logger.info(f"OKX WebSocket K 线订阅：{symbol} {interval}")

    async def _ws_ticker_loop(self, symbol: str):
        """WebSocket 行情循环"""
        while True:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    # 订阅
                    sub_msg = {
                        "op": "subscribe",
                        "args": [{
                            "channel": "tickers",
                            "instId": symbol
                        }]
                    }
                    await ws.send(json.dumps(sub_msg))
                    logger.info(f"OKX WebSocket 已连接并订阅：{symbol}")

                    # 等待订阅确认
                    while True:
                        message = await asyncio.wait_for(ws.recv(), timeout=60)
                        data = json.loads(message)

                        # 订阅确认
                        if data.get("event") == "subscribe":
                            logger.debug(f"OKX 订阅确认：{data}")
                            continue

                        # 推送数据
                        if data.get("arg", {}).get("channel") == "tickers" and data.get("data"):
                            for ticker_data in data["data"]:
                                ticker = Ticker(
                                    symbol=ticker_data.get("instId", symbol),
                                    last=float(ticker_data.get("last", 0)),
                                    bid=float(ticker_data.get("bidPx", 0)),
                                    ask=float(ticker_data.get("askPx", 0)),
                                    high=float(ticker_data.get("high24h", 0)),
                                    low=float(ticker_data.get("low24h", 0)),
                                    volume=float(ticker_data.get("vol24h", 0)),
                                    timestamp=datetime.fromtimestamp(int(ticker_data.get("ts", 0)) / 1000),
                                )

                                # 调用回调
                                if symbol in self.ticker_callbacks:
                                    for cb in self.ticker_callbacks[symbol]:
                                        if asyncio.iscoroutinefunction(cb):
                                            await cb(ticker)
                                        else:
                                            cb(ticker)

            except asyncio.CancelledError:
                logger.info(f"OKX WebSocket 取消：{symbol}")
                break
            except Exception as e:
                logger.error(f"OKX WebSocket 错误：{e}")
                await asyncio.sleep(5)  # 重连等待

    async def _ws_kline_loop(self, symbol: str, interval: str):
        """WebSocket K 线循环"""
        # OKX K 线间隔映射
        interval_map = {
            "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "1H", "4h": "4H", "1d": "1D", "1w": "1W",
        }
        kline_interval = interval_map.get(interval, "1H")

        while True:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    # 订阅
                    sub_msg = {
                        "op": "subscribe",
                        "args": [{
                            "channel": "candle" + kline_interval,
                            "instId": symbol
                        }]
                    }
                    await ws.send(json.dumps(sub_msg))
                    logger.info(f"OKX WebSocket K 线已连接并订阅：{symbol} {interval}")

                    while True:
                        message = await asyncio.wait_for(ws.recv(), timeout=60)
                        data = json.loads(message)

                        # 订阅确认
                        if data.get("event") == "subscribe":
                            logger.debug(f"OKX K 线订阅确认：{data}")
                            continue

                        # 推送数据
                        if "candle" in data.get("arg", {}).get("channel", "") and data.get("data"):
                            for candle_data in data["data"]:
                                # OKX K 线格式：[ts, o, h, l, c, vol, volCcy, volCcyQuote, trades]
                                kline = KLine(
                                    symbol=candle_data.get("instId", symbol),
                                    interval=interval,
                                    timestamp=datetime.fromtimestamp(int(candle_data[0]) / 1000) if isinstance(candle_data, list) else datetime.fromtimestamp(int(candle_data.get("ts", 0)) / 1000),
                                    open=float(candle_data[1]) if isinstance(candle_data, list) else float(candle_data.get("o", 0)),
                                    high=float(candle_data[2]) if isinstance(candle_data, list) else float(candle_data.get("h", 0)),
                                    low=float(candle_data[3]) if isinstance(candle_data, list) else float(candle_data.get("l", 0)),
                                    close=float(candle_data[4]) if isinstance(candle_data, list) else float(candle_data.get("c", 0)),
                                    volume=float(candle_data[5]) if isinstance(candle_data, list) else float(candle_data.get("vol", 0)),
                                )

                                # 调用回调
                                if symbol in self.kline_callbacks and interval in self.kline_callbacks[symbol]:
                                    for cb in self.kline_callbacks[symbol][interval]:
                                        if asyncio.iscoroutinefunction(cb):
                                            await cb(kline)
                                        else:
                                            cb(kline)

            except asyncio.CancelledError:
                logger.info(f"OKX WebSocket K 线取消：{symbol}")
                break
            except Exception as e:
                logger.error(f"OKX WebSocket K 线错误：{e}")
                await asyncio.sleep(5)  # 重连等待

    async def unsubscribe_ticker(self, symbol: str):
        """取消订阅行情"""
        if symbol in self.ws_tasks:
            self.ws_tasks[symbol].cancel()
            del self.ws_tasks[symbol]
        if symbol in self.ticker_callbacks:
            del self.ticker_callbacks[symbol]
        logger.info(f"OKX WebSocket 取消订阅：{symbol}")

    async def unsubscribe_klines(self, symbol: str, interval: str):
        """取消订阅 K 线"""
        if symbol in self.ws_tasks:
            self.ws_tasks[symbol].cancel()
            del self.ws_tasks[symbol]
        if symbol in self.kline_callbacks:
            if interval in self.kline_callbacks[symbol]:
                del self.kline_callbacks[symbol][interval]
        logger.info(f"OKX WebSocket 取消订阅 K 线：{symbol} {interval}")

    def _parse_order(self, order: Dict) -> Order:
        """解析订单"""
        status_map = {
            "open": OrderStatus.OPEN,
            "closed": OrderStatus.CLOSED,
            "canceled": OrderStatus.CANCELED,
            "expired": OrderStatus.EXPIRED,
            "rejected": OrderStatus.REJECTED,
        }

        return Order(
            id=str(order["id"]),
            symbol=order["symbol"],
            side=OrderSide(order["side"]),
            type=OrderType(order["type"]),
            amount=order["amount"],
            price=order.get("price"),
            status=status_map.get(order["status"], OrderStatus.PENDING),
            filled=order.get("filled", 0),
            remaining=order.get("remaining", 0),
            cost=order.get("cost", 0),
            fee=order.get("fee", {}).get("cost", 0),
            timestamp=datetime.fromtimestamp(order["timestamp"] / 1000),
            info=order.get("info"),
        )
