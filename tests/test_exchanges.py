"""
测试交易所接口
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.exchanges.base import (
    Order, OrderSide, OrderType, OrderStatus,
    Position, Ticker, KLine
)


class TestOrder:
    """测试订单"""

    def test_order_creation(self):
        """测试订单创建"""
        order = Order(
            id="123",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=0.1,
        )

        assert order.id == "123"
        assert order.symbol == "BTC/USDT"
        assert order.side == OrderSide.BUY
        assert order.amount == 0.1
        assert order.status == OrderStatus.PENDING
        assert order.remaining == 0.1

    def test_order_with_price(self):
        """测试限价订单"""
        order = Order(
            id="124",
            symbol="ETH/USDT",
            side=OrderSide.SELL,
            type=OrderType.LIMIT,
            amount=1.0,
            price=2000.0,
        )

        assert order.price == 2000.0
        assert order.side == OrderSide.SELL

    def test_order_filled(self):
        """测试已成交订单"""
        order = Order(
            id="125",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=0.1,
            filled=0.05,
            remaining=0.05,
        )

        assert order.filled == 0.05
        assert order.remaining == 0.05


class TestPosition:
    """测试持仓"""

    def test_position_creation(self):
        """测试持仓创建"""
        position = Position(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            amount=0.1,
            entry_price=50000.0,
            current_price=51000.0,
        )

        assert position.symbol == "BTC/USDT"
        assert position.amount == 0.1
        assert position.entry_price == 50000.0
        assert position.unrealized_pnl == 100.0  # (51000 - 50000) * 0.1

    def test_position_short(self):
        """测试空头持仓"""
        position = Position(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            amount=0.1,
            entry_price=50000.0,
            current_price=49000.0,
        )

        assert position.unrealized_pnl == 100.0  # (50000 - 49000) * 0.1

    def test_position_loss(self):
        """测试亏损持仓"""
        position = Position(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            amount=0.1,
            entry_price=50000.0,
            current_price=48000.0,
        )

        assert position.unrealized_pnl == -200.0  # (48000 - 50000) * 0.1

    def test_update_pnl(self):
        """测试更新盈亏"""
        position = Position(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            amount=0.1,
            entry_price=50000.0,
            current_price=51000.0,
        )

        # 更新价格
        position.current_price = 52000.0
        position.update_pnl()

        assert position.unrealized_pnl == 200.0  # (52000 - 50000) * 0.1


class TestTicker:
    """测试行情"""

    def test_ticker_creation(self):
        """测试行情创建"""
        ticker = Ticker(
            symbol="BTC/USDT",
            last=50000.0,
            bid=49999.0,
            ask=50001.0,
            high=51000.0,
            low=49000.0,
            volume=1000.0,
        )

        assert ticker.symbol == "BTC/USDT"
        assert ticker.last == 50000.0
        assert ticker.bid == 49999.0
        assert ticker.ask == 50001.0


class TestKLine:
    """测试 K 线"""

    def test_kline_creation(self):
        """测试 K 线创建"""
        kline = KLine(
            symbol="BTC/USDT",
            interval="1h",
            timestamp=datetime.now(),
            open=50000.0,
            high=50500.0,
            low=49500.0,
            close=50200.0,
            volume=500.0,
        )

        assert kline.symbol == "BTC/USDT"
        assert kline.interval == "1h"
        assert kline.open == 50000.0
        assert kline.high == 50500.0
        assert kline.low == 49500.0
        assert kline.close == 50200.0


class TestOrderSide:
    """测试订单方向"""

    def test_order_side_values(self):
        """测试订单方向值"""
        assert OrderSide.BUY.value == "buy"
        assert OrderSide.SELL.value == "sell"


class TestOrderType:
    """测试订单类型"""

    def test_order_type_values(self):
        """测试订单类型值"""
        assert OrderType.MARKET.value == "market"
        assert OrderType.LIMIT.value == "limit"
        assert OrderType.STOP_LOSS.value == "stop_loss"
        assert OrderType.TAKE_PROFIT.value == "take_profit"


class TestOrderStatus:
    """测试订单状态"""

    def test_order_status_values(self):
        """测试订单状态值"""
        assert OrderStatus.PENDING.value == "pending"
        assert OrderStatus.OPEN.value == "open"
        assert OrderStatus.CLOSED.value == "closed"
        assert OrderStatus.CANCELED.value == "canceled"


class MockExchange:
    """模拟交易所用于测试"""

    def __init__(self):
        self.name = "mock"
        self.connected = False
        self.orders = {}

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.connected = False

    async def get_ticker(self, symbol: str) -> Ticker:
        return Ticker(
            symbol=symbol,
            last=50000.0,
            bid=49999.0,
            ask=50001.0,
            high=51000.0,
            low=49000.0,
            volume=1000.0,
        )

    async def get_klines(self, symbol: str, interval: str = "1h", limit: int = 100):
        klines = []
        for i in range(limit):
            klines.append(KLine(
                symbol=symbol,
                interval=interval,
                timestamp=datetime.now(),
                open=50000.0 + i,
                high=50500.0 + i,
                low=49500.0 + i,
                close=50200.0 + i,
                volume=500.0,
            ))
        return klines

    async def get_balance(self):
        return {"BTC": 1.0, "USDT": 10000.0}

    async def get_positions(self):
        return []

    async def create_order(self, symbol, side, order_type, amount, price=None):
        order_id = f"order_{len(self.orders)}"
        order = Order(
            id=order_id,
            symbol=symbol,
            side=side,
            type=order_type,
            amount=amount,
            price=price,
            status=OrderStatus.OPEN,
        )
        self.orders[order_id] = order
        return order

    async def cancel_order(self, order_id, symbol):
        if order_id in self.orders:
            self.orders[order_id].status = OrderStatus.CANCELED
            return True
        return False

    async def get_order(self, order_id, symbol):
        return self.orders.get(order_id)

    async def get_open_orders(self, symbol=None):
        return [o for o in self.orders.values() if o.status == OrderStatus.OPEN]

    async def subscribe_ticker(self, symbol, callback):
        pass

    async def subscribe_klines(self, symbol, interval, callback):
        pass


class TestMockExchange:
    """测试模拟交易所"""

    @pytest.fixture
    def exchange(self):
        return MockExchange()

    @pytest.mark.asyncio
    async def test_connect(self, exchange):
        """测试连接"""
        await exchange.connect()
        assert exchange.connected is True

    @pytest.mark.asyncio
    async def test_get_ticker(self, exchange):
        """测试获取行情"""
        await exchange.connect()
        ticker = await exchange.get_ticker("BTC/USDT")

        assert ticker.symbol == "BTC/USDT"
        assert ticker.last == 50000.0

    @pytest.mark.asyncio
    async def test_get_klines(self, exchange):
        """测试获取 K 线"""
        await exchange.connect()
        klines = await exchange.get_klines("BTC/USDT", "1h", limit=10)

        assert len(klines) == 10
        assert all(k.symbol == "BTC/USDT" for k in klines)

    @pytest.mark.asyncio
    async def test_create_order(self, exchange):
        """测试创建订单"""
        await exchange.connect()
        order = await exchange.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=0.1,
        )

        assert order.id.startswith("order_")
        assert order.side == OrderSide.BUY
        assert order.amount == 0.1

    @pytest.mark.asyncio
    async def test_cancel_order(self, exchange):
        """测试取消订单"""
        await exchange.connect()
        order = await exchange.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=0.1,
        )

        result = await exchange.cancel_order(order.id, "BTC/USDT")
        assert result is True
        assert order.status == OrderStatus.CANCELED

    @pytest.mark.asyncio
    async def test_get_balance(self, exchange):
        """测试获取余额"""
        await exchange.connect()
        balance = await exchange.get_balance()

        assert "BTC" in balance
        assert "USDT" in balance
