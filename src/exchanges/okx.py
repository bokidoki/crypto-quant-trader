"""
OKX 交易所接口
"""
from typing import Dict, List, Optional, Callable
from datetime import datetime

import ccxt.async_support as ccxt
from loguru import logger

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
            logger.info(f"OKX 使用代理: {self.settings.proxy.http}")
        
        # 加载市场
        await self.client.load_markets()
        
        self.connected = True
        logger.info(f"OKX 已连接，市场数: {len(self.client.markets)}")
    
    async def disconnect(self):
        """断开连接"""
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
        """获取K线"""
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
        
        logger.info(f"订单已创建: {order['id']} {side.value} {amount} {symbol}")
        
        return self._parse_order(order)
    
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        if not self.connected:
            raise RuntimeError("OKX 未连接")
        
        try:
            await self.client.cancel_order(order_id, symbol)
            logger.info(f"订单已取消: {order_id}")
            return True
        except Exception as e:
            logger.error(f"取消订单失败: {order_id}, 错误: {e}")
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
        logger.warning("OKX WebSocket 订阅待实现")
    
    async def subscribe_klines(self, symbol: str, interval: str, callback: Callable):
        """订阅K线"""
        logger.warning("OKX WebSocket 订阅待实现")
    
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
