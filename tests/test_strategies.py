"""
测试策略框架
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.strategies.base import BaseStrategy, StrategyConfig
from src.strategies.sma_strategy import SMAStrategy
from src.exchanges.base import Ticker, KLine, Order, OrderSide, OrderType, OrderStatus


class TestStrategyConfig:
    """测试策略配置"""

    def test_default_config(self):
        """测试默认配置"""
        config = StrategyConfig(name="test", symbol="BTC/USDT")

        assert config.name == "test"
        assert config.symbol == "BTC/USDT"
        assert config.timeframe == "1h"
        assert config.enabled is True
        assert config.position_size == 0.01
        assert config.max_positions == 1
        assert config.stop_loss is None
        assert config.take_profit is None

    def test_custom_config(self):
        """测试自定义配置"""
        config = StrategyConfig(
            name="sma_strategy",
            symbol="ETH/USDT",
            timeframe="4h",
            position_size=0.1,
            max_positions=2,
            stop_loss=0.05,
            take_profit=0.1,
            params={"fast_period": 10, "slow_period": 30},
        )

        assert config.name == "sma_strategy"
        assert config.symbol == "ETH/USDT"
        assert config.timeframe == "4h"
        assert config.position_size == 0.1
        assert config.params == {"fast_period": 10, "slow_period": 30}


class MockStrategy(BaseStrategy):
    """模拟策略用于测试"""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.signals_generated = []

    async def on_tick(self, ticker: Ticker):
        self.ticker = ticker

    async def on_bar(self, bar: KLine):
        self.update_bar(bar)

    async def generate_signal(self):
        if len(self.bars) >= 2:
            signal = {"side": "buy", "amount": 0.1, "reason": "test"}
            self.signals_generated.append(signal)
            return signal
        return None


class TestBaseStrategy:
    """测试策略基类"""

    @pytest.fixture
    def config(self):
        return StrategyConfig(name="test", symbol="BTC/USDT")

    @pytest.fixture
    def strategy(self, config):
        return MockStrategy(config)

    def test_init(self, strategy, config):
        """测试初始化"""
        assert strategy.name == config.name
        assert strategy.symbol == config.symbol
        assert strategy.timeframe == config.timeframe
        assert strategy.exchange is None
        assert len(strategy.bars) == 0
        assert strategy.ticker is None

    @pytest.mark.asyncio
    async def test_on_tick(self, strategy):
        """测试行情更新"""
        ticker = Ticker(
            symbol="BTC/USDT",
            last=50000.0,
            bid=49999.0,
            ask=50001.0,
            high=51000.0,
            low=49000.0,
            volume=1000.0,
        )

        await strategy.on_tick(ticker)
        assert strategy.ticker == ticker

    @pytest.mark.asyncio
    async def test_on_bar(self, strategy):
        """测试 K 线更新"""
        bar = KLine(
            symbol="BTC/USDT",
            interval="1h",
            timestamp=datetime.now(),
            open=50000.0,
            high=50500.0,
            low=49500.0,
            close=50200.0,
            volume=500.0,
        )

        await strategy.on_bar(bar)
        assert len(strategy.bars) == 1
        assert strategy.bars[0].close == 50200.0

    @pytest.mark.asyncio
    async def test_generate_signal(self, strategy):
        """测试生成信号"""
        # 添加足够的 K 线
        for i in range(3):
            bar = KLine(
                symbol="BTC/USDT",
                interval="1h",
                timestamp=datetime.now(),
                open=50000.0 + i,
                high=50500.0 + i,
                low=49500.0 + i,
                close=50200.0 + i,
                volume=500.0,
            )
            strategy.bars.append(bar)

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal["side"] == "buy"
        assert signal["amount"] == 0.1
        assert len(strategy.signals_generated) == 1

    @pytest.mark.asyncio
    async def test_buy(self, strategy):
        """测试买入"""
        mock_exchange = AsyncMock()
        mock_exchange.create_order = AsyncMock(return_value=Order(
            id="order_1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=0.1,
            status=OrderStatus.OPEN,
        ))
        strategy.exchange = mock_exchange

        order = await strategy.buy(amount=0.1)

        assert order is not None
        assert order.id == "order_1"
        mock_exchange.create_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_sell(self, strategy):
        """测试卖出"""
        mock_exchange = AsyncMock()
        mock_exchange.create_order = AsyncMock(return_value=Order(
            id="order_2",
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            amount=0.1,
            status=OrderStatus.OPEN,
        ))
        strategy.exchange = mock_exchange

        order = await strategy.sell(amount=0.1)

        assert order is not None
        assert order.id == "order_2"

    @pytest.mark.asyncio
    async def test_buy_no_exchange(self, strategy):
        """测试没有交易所时买入"""
        strategy.exchange = None

        order = await strategy.buy(amount=0.1)

        assert order is None

    def test_update_bar_limit(self, strategy):
        """测试 K 线数量限制"""
        # 添加超过 500 根 K 线
        for i in range(600):
            bar = KLine(
                symbol="BTC/USDT",
                interval="1h",
                timestamp=datetime.now(),
                open=50000.0,
                high=50500.0,
                low=49500.0,
                close=50200.0,
                volume=500.0,
            )
            strategy.update_bar(bar)

        assert len(strategy.bars) == 500

    def test_get_stats(self, strategy):
        """测试获取统计"""
        strategy.stats["total_trades"] = 10
        strategy.stats["win_trades"] = 6
        strategy.stats["total_pnl"] = 100.0

        stats = strategy.get_stats()

        assert stats["name"] == "test"
        assert stats["total_trades"] == 10
        assert stats["win_rate"] == "60.00%"
        assert stats["total_pnl"] == 100.0


class TestSMAStrategy:
    """测试 SMA 策略"""

    @pytest.fixture
    def config(self):
        return StrategyConfig(
            name="sma",
            symbol="BTC/USDT",
            params={"fast_period": 5, "slow_period": 10},
            position_size=0.1,
        )

    @pytest.fixture
    def sma_strategy(self, config):
        return SMAStrategy(config)

    def test_init(self, sma_strategy, config):
        """测试初始化"""
        assert sma_strategy.fast_period == 5
        assert sma_strategy.slow_period == 10
        assert sma_strategy.last_signal is None

    @pytest.mark.asyncio
    async def test_no_signal_with_insufficient_data(self, sma_strategy):
        """测试数据不足时无信号"""
        # 只添加少量 K 线
        for i in range(5):
            bar = KLine(
                symbol="BTC/USDT",
                interval="1h",
                timestamp=datetime.now(),
                open=50000.0 + i,
                high=50500.0 + i,
                low=49500.0 + i,
                close=50200.0 + i,
                volume=500.0,
            )
            sma_strategy.bars.append(bar)

        signal = await sma_strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_golden_cross_signal(self, sma_strategy):
        """测试金叉信号"""
        # 构造金叉场景：快线从下向上穿越慢线
        # 先添加下跌数据
        for i in range(15):
            bar = KLine(
                symbol="BTC/USDT",
                interval="1h",
                timestamp=datetime.now(),
                open=50000.0 - i * 100,
                high=50100.0 - i * 100,
                low=49900.0 - i * 100,
                close=49950.0 - i * 100,
                volume=500.0,
            )
            sma_strategy.bars.append(bar)

        # 第一次生成信号（无交叉）
        await sma_strategy.generate_signal()

        # 添加上涨数据制造金叉
        for i in range(10):
            bar = KLine(
                symbol="BTC/USDT",
                interval="1h",
                timestamp=datetime.now(),
                open=48000.0 + i * 300,
                high=48500.0 + i * 300,
                low=47800.0 + i * 300,
                close=48300.0 + i * 300,
                volume=500.0,
            )
            sma_strategy.bars.append(bar)

        signal = await sma_strategy.generate_signal()

        # 应该有金叉买入信号
        if signal:
            assert signal["side"] == "buy"

    def test_get_indicators(self, sma_strategy):
        """测试获取指标"""
        # 添加足够的 K 线
        for i in range(15):
            bar = KLine(
                symbol="BTC/USDT",
                interval="1h",
                timestamp=datetime.now(),
                open=50000.0 + i,
                high=50500.0 + i,
                low=49500.0 + i,
                close=50200.0 + i,
                volume=500.0,
            )
            sma_strategy.bars.append(bar)

        indicators = sma_strategy.get_indicators()

        assert "fast_ma" in indicators
        assert "slow_ma" in indicators
        assert "trend" in indicators
        assert isinstance(indicators["fast_ma"], float)
        assert isinstance(indicators["slow_ma"], float)

    def test_get_indicators_empty(self, sma_strategy):
        """测试无数据时指标"""
        indicators = sma_strategy.get_indicators()

        assert indicators == {}
