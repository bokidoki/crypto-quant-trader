"""
Binance 交易所接口
"""
import asyncio
import json
from typing import Dict, List, Optional, Any, Callable, Set
from datetime import datetime
from enum import Enum

import ccxt.async_support as ccxt
from loguru import logger
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from .base import (
    BaseExchange, Order, OrderSide, OrderType, OrderStatus,
    Position, Ticker, KLine
)
from ..core.config import get_settings


class WsStreamType(str, Enum):
    """WebSocket 流类型"""
    TICKER = "ticker"
    KLINE = "kline"


class BinanceExchange(BaseExchange):
    """
    Binance 交易所实现

    支持现货交易，使用 ccxt 库。
    """

    # Binance WebSocket 公共流 URL
    WS_URL = "wss://stream.binance.com:9443/ws"
    # 心跳间隔（秒）
    HEARTBEAT_INTERVAL = 30
    # 重连最大重试次数
    MAX_RECONNECT_ATTEMPTS = 5
    # 重连间隔（秒）
    RECONNECT_DELAY = 5

    def __init__(self):
        super().__init__("binance")
        self.settings = get_settings()
        self.client: Optional[ccxt.binance] = None

        # WebSocket 连接管理 - 单一连接管理所有订阅
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._ws_connected = False
        self._ws_task: Optional[asyncio.Task] = None
        self._ws_subscriptions: Set[str] = set()  # 已订阅的流名称

        # 回调函数管理
        self._ticker_callbacks: Dict[str, List[Callable]] = {}
        self._kline_callbacks: Dict[str, Dict[str, List[Callable]]] = {}

        # 心跳相关
        self._last_pong_time: Optional[float] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

        # 取消事件 - 用于优雅关闭
        self._close_event = asyncio.Event()

    async def connect(self):
        """连接 Binance"""
        config = self.settings.binance

        if not config.enabled:
            logger.info("Binance 未启用")
            return

        self.client = ccxt.binance(
            {
                "apiKey": config.api_key,
                "secret": config.api_secret,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "spot",
                },
            }
        )

        # 测试网设置
        if config.testnet:
            self.client.set_sandbox_mode(True)
            logger.info("Binance 测试网模式")

        # 代理设置 (ccxt 异步版本使用 aiohttp_proxy)
        if self.settings.proxy.enabled:
            self.client.aiohttp_proxy = self.settings.proxy.http
            logger.info(f"Binance 使用代理：{self.settings.proxy.http}")

        # 加载市场
        await self.client.load_markets()

        self.connected = True
        logger.info(f"Binance 已连接，市场数：{len(self.client.markets)}")

    # ==================== WebSocket 管理核心方法 ====================

    def _generate_stream_name(self, symbol: str, stream_type: WsStreamType, interval: Optional[str] = None) -> str:
        """生成 WebSocket 流名称"""
        symbol_lower = symbol.lower()
        if stream_type == WsStreamType.TICKER:
            return f"{symbol_lower}@ticker"
        elif stream_type == WsStreamType.KLINE:
            interval_map = {
                "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m",
                "30m": "30m", "1h": "1h", "2h": "2h", "4h": "4h",
                "6h": "6h", "8h": "8h", "12h": "12h", "1d": "1d",
                "3d": "3d", "1w": "1w", "1M": "1M",
            }
            kline_interval = interval_map.get(interval, "1h")
            return f"{symbol_lower}@kline_{kline_interval}"
        raise ValueError(f"不支持的流类型：{stream_type}")

    async def _ensure_ws_connection(self):
        """确保 WebSocket 连接存在"""
        if self._ws is not None and self._ws_connected:
            return

        await self._connect_ws()

    async def _connect_ws(self):
        """建立 WebSocket 连接"""
        try:
            self._ws = await websockets.connect(
                self.WS_URL,
                ping_interval=self.HEARTBEAT_INTERVAL,
                ping_timeout=10,
                close_timeout=5,
            )
            self._ws_connected = True
            self._last_pong_time = datetime.now().timestamp()
            logger.info(f"Binance WebSocket 已连接：{self.WS_URL}")

            # 重新订阅之前的订阅
            if self._ws_subscriptions:
                subscribe_msg = {
                    "method": "SUBSCRIBE",
                    "params": list(self._ws_subscriptions),
                    "id": len(self._ws_subscriptions),
                }
                await self._ws.send(json.dumps(subscribe_msg))
                logger.info(f"Binance WebSocket 重新订阅 {len(self._ws_subscriptions)} 个流")

            # 启动心跳监控
            if self._heartbeat_task is None or self._heartbeat_task.done():
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            # 启动消息接收循环
            if self._ws_task is None or self._ws_task.done():
                self._ws_task = asyncio.create_task(self._ws_receive_loop())

        except Exception as e:
            logger.error(f"Binance WebSocket 连接失败：{e}")
            self._ws_connected = False
            raise

    async def _subscribe_stream(self, stream_name: str):
        """订阅单个流"""
        if stream_name in self._ws_subscriptions:
            return  # 已订阅

        if not self._ws_connected:
            await self._ensure_ws_connection()

        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": [stream_name],
            "id": int(datetime.now().timestamp() * 1000),
        }

        try:
            await self._ws.send(json.dumps(subscribe_msg))
            self._ws_subscriptions.add(stream_name)
            logger.debug(f"Binance WebSocket 订阅：{stream_name}")
        except Exception as e:
            logger.error(f"Binance WebSocket 订阅失败 {stream_name}: {e}")
            raise

    async def _unsubscribe_stream(self, stream_name: str):
        """取消订阅单个流"""
        if stream_name not in self._ws_subscriptions:
            return

        unsubscribe_msg = {
            "method": "UNSUBSCRIBE",
            "params": [stream_name],
            "id": int(datetime.now().timestamp() * 1000),
        }

        try:
            await self._ws.send(json.dumps(unsubscribe_msg))
            self._ws_subscriptions.discard(stream_name)
            logger.debug(f"Binance WebSocket 取消订阅：{stream_name}")
        except Exception as e:
            logger.error(f"Binance WebSocket 取消订阅失败 {stream_name}: {e}")

    async def _heartbeat_loop(self):
        """心跳循环 - 监控连接健康状态"""
        while not self._close_event.is_set():
            try:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)

                if not self._ws_connected:
                    continue

                # 检查是否收到 pong
                if self._last_pong_time:
                    elapsed = datetime.now().timestamp() - self._last_pong_time
                    if elapsed > self.HEARTBEAT_INTERVAL * 2:
                        logger.warning("Binance WebSocket 心跳超时，尝试重连")
                        self._ws_connected = False
                        await self._reconnect_ws()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Binance WebSocket 心跳错误：{e}")

    async def _reconnect_ws(self):
        """重连 WebSocket"""
        attempt = 0
        while attempt < self.MAX_RECONNECT_ATTEMPTS and not self._close_event.is_set():
            attempt += 1
            try:
                logger.info(f"Binance WebSocket 重连尝试 {attempt}/{self.MAX_RECONNECT_ATTEMPTS}")

                if self._ws:
                    await self._ws.close()

                await asyncio.sleep(self.RECONNECT_DELAY)
                await self._connect_ws()
                logger.info("Binance WebSocket 重连成功")
                return

            except Exception as e:
                logger.error(f"Binance WebSocket 重连失败：{e}")
                if attempt >= self.MAX_RECONNECT_ATTEMPTS:
                    logger.error("Binance WebSocket 达到最大重连次数")
                    self._ws_connected = False

    async def _ws_receive_loop(self):
        """WebSocket 消息接收循环"""
        while not self._close_event.is_set():
            try:
                if not self._ws or not self._ws_connected:
                    await asyncio.sleep(1)
                    continue

                message = await asyncio.wait_for(self._ws.recv(), timeout=self.HEARTBEAT_INTERVAL * 2)
                await self._handle_ws_message(message)

            except asyncio.TimeoutError:
                # 超时，继续等待
                continue
            except asyncio.CancelledError:
                logger.info("Binance WebSocket 接收循环取消")
                break
            except ConnectionClosed as e:
                logger.warning(f"Binance WebSocket 连接关闭：{e}")
                self._ws_connected = False
                await self._reconnect_ws()
            except WebSocketException as e:
                logger.error(f"Binance WebSocket 异常：{e}")
                self._ws_connected = False
                await asyncio.sleep(self.RECONNECT_DELAY)
            except Exception as e:
                logger.error(f"Binance WebSocket 错误：{e}")
                await asyncio.sleep(self.RECONNECT_DELAY)

    async def _handle_ws_message(self, message: str):
        """处理 WebSocket 消息"""
        try:
            data = json.loads(message)

            # 处理订阅响应
            if "result" in data or "id" in data:
                if data.get("result") is not None:
                    logger.debug(f"Binance WebSocket 响应：{data}")
                return

            # 处理 24 小时行情 Ticker
            if "e" in data and data["e"] == "24hrTicker":
                ticker = Ticker(
                    symbol=data["s"],
                    last=float(data["c"]),
                    bid=float(data["b"]),
                    ask=float(data["a"]),
                    high=float(data["h"]),
                    low=float(data["l"]),
                    volume=float(data["v"]),
                    quote_volume=float(data.get("q", 0)),
                    timestamp=datetime.fromtimestamp(data["E"] / 1000),
                )
                symbol = data["s"].lower()
                if symbol in self._ticker_callbacks:
                    for cb in self._ticker_callbacks[symbol]:
                        if asyncio.iscoroutinefunction(cb):
                            await cb(ticker)
                        else:
                            cb(ticker)
                return

            # 处理 K 线数据
            if "k" in data:
                k = data["k"]
                kline = KLine(
                    symbol=data["s"],
                    interval=self._resolve_kline_interval(k["i"]),
                    timestamp=datetime.fromtimestamp(k["t"] / 1000),
                    open=float(k["o"]),
                    high=float(k["h"]),
                    low=float(k["l"]),
                    close=float(k["c"]),
                    volume=float(k["v"]),
                    quote_volume=float(k.get("q", 0)),
                    is_closed=not k["x"],  # x=False 表示 K 线未闭合
                )
                symbol = data["s"].lower()
                interval = self._resolve_kline_interval(k["i"])
                if symbol in self._kline_callbacks and interval in self._kline_callbacks[symbol]:
                    for cb in self._kline_callbacks[symbol][interval]:
                        if asyncio.iscoroutinefunction(cb):
                            await cb(kline)
                        else:
                            cb(kline)
                return

            # 处理 pong 响应
            if "pong" in data:
                self._last_pong_time = datetime.now().timestamp()

        except json.JSONDecodeError as e:
            logger.error(f"Binance WebSocket 消息解析失败：{e}")
        except Exception as e:
            logger.error(f"Binance WebSocket 消息处理错误：{e}")

    def _resolve_kline_interval(self, kline_i: str) -> str:
        """解析 K 线间隔"""
        # Binance 返回的间隔格式与输入保持一致
        return kline_i

    async def disconnect(self):
        """断开连接"""
        self._close_event.set()

        # 取消心跳任务
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # 取消 WebSocket 接收任务
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

        # 关闭 WebSocket 连接
        if self._ws:
            await self._ws.close()

        # 清空状态
        self._ws = None
        self._ws_connected = False
        self._ws_subscriptions.clear()
        self._ticker_callbacks.clear()
        self._kline_callbacks.clear()

        if self.client:
            await self.client.close()
            self.connected = False
            logger.info("Binance 已断开")

    async def get_ticker(self, symbol: str) -> Ticker:
        """获取行情"""
        if not self.connected:
            raise RuntimeError("Binance 未连接")

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
            raise RuntimeError("Binance 未连接")

        # ccxt 使用 timeframe 格式：1m, 5m, 15m, 1h, 4h, 1d
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
            raise RuntimeError("Binance 未连接")

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
        """获取持仓（现货无持仓概念，返回余额）"""
        # 现货交易没有持仓概念，这里返回空列表
        # 如果需要合约交易，需要修改 client 配置为 "future"
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
            raise RuntimeError("Binance 未连接")

        # 映射订单类型
        type_map = {
            OrderType.MARKET: "market",
            OrderType.LIMIT: "limit",
            OrderType.STOP_LOSS: "stop_market",
            OrderType.STOP_LOSS_LIMIT: "stop_limit",
            OrderType.TAKE_PROFIT: "take_profit_market",
            OrderType.TAKE_PROFIT_LIMIT: "take_profit_limit",
        }

        params = {}
        if order_type in [OrderType.STOP_LOSS, OrderType.STOP_LOSS_LIMIT,
                          OrderType.TAKE_PROFIT, OrderType.TAKE_PROFIT_LIMIT]:
            if price is None:
                raise ValueError(f"{order_type.value} 需要提供触发价格")
            params["stopPrice"] = price

        # 创建订单
        order = await self.client.create_order(
            symbol=symbol,
            type=type_map.get(order_type, "market"),
            side=side.value,
            amount=amount,
            price=price if order_type in [OrderType.LIMIT, OrderType.STOP_LOSS_LIMIT,
                                           OrderType.TAKE_PROFIT_LIMIT] else None,
            params=params if params else None,
        )

        logger.info(f"订单已创建：{order['id']} {side.value} {amount} {symbol}")

        return self._parse_order(order)

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        if not self.connected:
            raise RuntimeError("Binance 未连接")

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
            raise RuntimeError("Binance 未连接")

        order = await self.client.fetch_order(order_id, symbol)
        return self._parse_order(order)

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """获取未完成订单"""
        if not self.connected:
            raise RuntimeError("Binance 未连接")

        orders = await self.client.fetch_open_orders(symbol)
        return [self._parse_order(o) for o in orders]

    async def subscribe_ticker(self, symbol: str, callback: Callable):
        """
        订阅实时行情

        Args:
            symbol: 交易对，如 'BTC/USDT'
            callback: 回调函数，接收 Ticker 对象
        """
        symbol_upper = symbol.upper()
        symbol_key = symbol_upper.lower()

        if symbol_key not in self._ticker_callbacks:
            self._ticker_callbacks[symbol_key] = []
        self._ticker_callbacks[symbol_key].append(callback)

        # 生成流名称并订阅
        stream_name = self._generate_stream_name(symbol_upper, WsStreamType.TICKER)
        await self._subscribe_stream(stream_name)
        logger.info(f"Binance 行情订阅：{symbol}")

    async def subscribe_klines(self, symbol: str, interval: str, callback: Callable):
        """
        订阅 K 线数据

        Args:
            symbol: 交易对，如 'BTC/USDT'
            interval: K 线间隔，支持 1m, 5m, 15m, 30m, 1h, 4h, 1d 等
            callback: 回调函数，接收 KLine 对象
        """
        symbol_upper = symbol.upper()
        symbol_key = symbol_upper.lower()

        if symbol_key not in self._kline_callbacks:
            self._kline_callbacks[symbol_key] = {}
        if interval not in self._kline_callbacks[symbol_key]:
            self._kline_callbacks[symbol_key][interval] = []
        self._kline_callbacks[symbol_key][interval].append(callback)

        # 生成流名称并订阅
        stream_name = self._generate_stream_name(symbol_upper, WsStreamType.KLINE, interval)
        await self._subscribe_stream(stream_name)
        logger.info(f"Binance K 线订阅：{symbol} {interval}")

    async def unsubscribe_ticker(self, symbol: str):
        """
        取消订阅行情

        Args:
            symbol: 交易对，如 'BTC/USDT'
        """
        symbol_upper = symbol.upper()
        symbol_key = symbol_upper.lower()

        # 移除回调
        if symbol_key in self._ticker_callbacks:
            del self._ticker_callbacks[symbol_key]

        # 取消 WebSocket 订阅
        stream_name = self._generate_stream_name(symbol_upper, WsStreamType.TICKER)
        await self._unsubscribe_stream(stream_name)

        logger.info(f"Binance 取消行情订阅：{symbol}")

    async def unsubscribe_klines(self, symbol: str, interval: str):
        """
        取消订阅 K 线

        Args:
            symbol: 交易对，如 'BTC/USDT'
            interval: K 线间隔
        """
        symbol_upper = symbol.upper()
        symbol_key = symbol_upper.lower()

        # 移除回调
        if symbol_key in self._kline_callbacks:
            if interval in self._kline_callbacks[symbol_key]:
                del self._kline_callbacks[symbol_key][interval]
            if not self._kline_callbacks[symbol_key]:
                del self._kline_callbacks[symbol_key]

        # 取消 WebSocket 订阅
        stream_name = self._generate_stream_name(symbol_upper, WsStreamType.KLINE, interval)
        await self._unsubscribe_stream(stream_name)

        logger.info(f"Binance 取消 K 线订阅：{symbol} {interval}")

    async def unsubscribe_all(self):
        """取消所有订阅并关闭 WebSocket"""
        await self.disconnect()
        logger.info("Binance 已取消所有订阅")

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
