"""
测试核心引擎和配置
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.engine import TradingEngine, EngineState
from src.core.config import Settings, load_settings, get_settings


class TestTradingEngine:
    """测试交易引擎"""

    @pytest.fixture
    def engine(self):
        """创建引擎实例"""
        return TradingEngine()

    def test_init(self, engine):
        """测试初始化"""
        assert engine.state == EngineState.STOPPED
        assert len(engine.exchanges) == 0
        assert len(engine.strategies) == 0
        assert engine.risk_manager is None
        assert len(engine.event_handlers) == 0

    def test_register_exchange(self, engine):
        """测试注册交易所"""
        mock_exchange = MagicMock()
        engine.register_exchange("binance", mock_exchange)

        assert "binance" in engine.exchanges
        assert engine.exchanges["binance"] == mock_exchange

    def test_register_strategy(self, engine):
        """测试注册策略"""
        mock_strategy = MagicMock()
        engine.register_strategy("sma", mock_strategy)

        assert "sma" in engine.strategies
        assert engine.strategies["sma"] == mock_strategy

    def test_set_risk_manager(self, engine):
        """测试设置风控管理器"""
        mock_risk_manager = MagicMock()
        engine.set_risk_manager(mock_risk_manager)

        assert engine.risk_manager == mock_risk_manager

    def test_on_event(self, engine):
        """测试注册事件处理器"""
        handler = MagicMock()
        engine.on("test_event", handler)

        assert "test_event" in engine.event_handlers
        assert handler in engine.event_handlers["test_event"]

    @pytest.mark.asyncio
    async def test_emit_event(self, engine):
        """测试触发事件"""
        handler = AsyncMock()
        engine.on("test_event", handler)

        await engine.emit("test_event", {"data": "test"})

        handler.assert_called_once_with({"data": "test"})

    @pytest.mark.asyncio
    async def test_start(self, engine):
        """测试启动引擎"""
        mock_exchange = AsyncMock()
        mock_exchange.connect = AsyncMock()
        mock_strategy = AsyncMock()
        mock_strategy.init = AsyncMock()

        engine.register_exchange("binance", mock_exchange)
        engine.register_strategy("sma", mock_strategy)

        await engine.start()

        assert engine.state == EngineState.RUNNING
        assert engine.stats["start_time"] is not None
        mock_exchange.connect.assert_called_once()
        mock_strategy.init.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop(self, engine):
        """测试停止引擎"""
        engine.state = EngineState.RUNNING

        mock_exchange = AsyncMock()
        mock_exchange.disconnect = AsyncMock()
        mock_strategy = AsyncMock()
        mock_strategy.stop = AsyncMock()

        engine.register_exchange("binance", mock_exchange)
        engine.register_strategy("sma", mock_strategy)

        await engine.stop()

        assert engine.state == EngineState.STOPPED
        mock_strategy.stop.assert_called_once()
        mock_exchange.disconnect.assert_called_once()

    def test_get_status(self, engine):
        """测试获取状态"""
        engine.register_exchange("binance", MagicMock())
        engine.register_strategy("sma", MagicMock())

        status = engine.get_status()

        assert "state" in status
        assert "exchanges" in status
        assert "strategies" in status
        assert "stats" in status
        assert status["exchanges"] == ["binance"]
        assert status["strategies"] == ["sma"]


class TestSettings:
    """测试配置管理"""

    def test_default_settings(self):
        """测试默认配置"""
        settings = Settings()

        assert settings.mode == "testnet"
        assert settings.proxy.enabled is True
        assert settings.binance.enabled is True
        assert settings.binance.testnet is True
        assert settings.risk.max_position == 100.0
        assert settings.risk.max_daily_loss == 50.0

    def test_load_settings_nonexistent(self):
        """测试加载不存在的配置文件"""
        settings = load_settings("nonexistent_path.yaml")

        assert isinstance(settings, Settings)

    def test_get_settings_singleton(self):
        """测试配置单例"""
        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2


class TestEngineState:
    """测试引擎状态"""

    def test_state_values(self):
        """测试状态值"""
        assert EngineState.STOPPED.value == "stopped"
        assert EngineState.STARTING.value == "starting"
        assert EngineState.RUNNING.value == "running"
        assert EngineState.STOPPING.value == "stopping"
        assert EngineState.ERROR.value == "error"
