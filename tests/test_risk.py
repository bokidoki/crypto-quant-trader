"""
测试风控模块
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.risk.manager import RiskManager, RiskStats
from src.exchanges.base import Order, OrderSide, OrderType, OrderStatus


class TestRiskStats:
    """测试风控统计"""

    def test_default_stats(self):
        """测试默认统计"""
        stats = RiskStats()

        assert stats.daily_pnl == 0.0
        assert stats.daily_trades == 0
        assert stats.total_positions == 0.0
        assert stats.max_position_reached == 0.0

    def test_stats_with_values(self):
        """测试带值的统计"""
        stats = RiskStats(
            daily_pnl=100.0,
            daily_trades=5,
            total_positions=500.0,
            max_position_reached=600.0,
        )

        assert stats.daily_pnl == 100.0
        assert stats.daily_trades == 5
        assert stats.total_positions == 500.0


class TestRiskManager:
    """测试风控管理器"""

    @pytest.fixture
    def risk_manager(self):
        return RiskManager()

    def test_init(self, risk_manager):
        """测试初始化"""
        assert risk_manager.stats is not None
        assert isinstance(risk_manager.stats, RiskStats)
        assert len(risk_manager.orders) == 0

    def test_check_order_pass(self, risk_manager):
        """测试订单检查通过"""
        order = Order(
            id="1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=0.1,
            price=50000.0,
        )

        passed, reason = risk_manager.check_order(order)

        assert passed is True
        assert reason == "通过"

    def test_check_order_position_limit(self, risk_manager):
        """测试仓位限制"""
        # 设置较小的仓位限制
        risk_manager.settings.max_position = 100.0

        order = Order(
            id="1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=1.0,
            price=500.0,  # 500 > 100
        )

        passed, reason = risk_manager.check_order(order)

        assert passed is False
        assert "超过限制" in reason

    def test_check_order_daily_loss_limit(self, risk_manager):
        """测试每日亏损限制"""
        # 设置已达到每日亏损限制
        risk_manager.settings.max_daily_loss = 50.0
        risk_manager.stats.daily_pnl = -60.0  # 超过限制

        order = Order(
            id="1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=0.1,
            price=50000.0,
        )

        passed, reason = risk_manager.check_order(order)

        assert passed is False
        assert "每日最大亏损" in reason

    def test_update_position_buy(self, risk_manager):
        """测试更新多头仓位"""
        order = Order(
            id="1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=0.1,
            price=50000.0,
            filled=0.1,
        )

        risk_manager.update_position(order)

        assert len(risk_manager.orders) == 1
        assert risk_manager.stats.daily_trades == 1
        assert risk_manager.stats.total_positions == 5000.0  # 0.1 * 50000

    def test_update_position_sell(self, risk_manager):
        """测试更新空头仓位"""
        order = Order(
            id="1",
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            amount=0.1,
            price=50000.0,
            filled=0.1,
        )

        risk_manager.update_position(order)

        assert risk_manager.stats.total_positions == -5000.0

    def test_update_pnl(self, risk_manager):
        """测试更新盈亏"""
        risk_manager.update_pnl(100.0)

        assert risk_manager.stats.daily_pnl == 100.0

        risk_manager.update_pnl(-50.0)

        assert risk_manager.stats.daily_pnl == 50.0

    def test_check_stop_loss_long(self, risk_manager):
        """测试多头止损"""
        risk_manager.settings.stop_loss_percent = 5.0

        # 亏损 6%，应该触发止损
        triggered = risk_manager.check_stop_loss(
            entry_price=100.0,
            current_price=94.0,
            side=OrderSide.BUY,
        )

        assert triggered is True

        # 亏损 4%，不应触发止损
        triggered = risk_manager.check_stop_loss(
            entry_price=100.0,
            current_price=96.0,
            side=OrderSide.BUY,
        )

        assert triggered is False

    def test_check_stop_loss_short(self, risk_manager):
        """测试空头止损"""
        risk_manager.settings.stop_loss_percent = 5.0

        # 价格上涨 6%，应该触发止损
        triggered = risk_manager.check_stop_loss(
            entry_price=100.0,
            current_price=106.0,
            side=OrderSide.SELL,
        )

        assert triggered is True

    def test_check_stop_loss_disabled(self, risk_manager):
        """测试止损禁用"""
        risk_manager.settings.stop_loss_percent = 0.0

        triggered = risk_manager.check_stop_loss(
            entry_price=100.0,
            current_price=50.0,
            side=OrderSide.BUY,
        )

        assert triggered is False

    def test_check_take_profit_long(self, risk_manager):
        """测试多头止盈"""
        risk_manager.settings.take_profit_percent = 10.0

        # 盈利 15%，应该触发止盈
        triggered = risk_manager.check_take_profit(
            entry_price=100.0,
            current_price=115.0,
            side=OrderSide.BUY,
        )

        assert triggered is True

        # 盈利 5%，不应触发止盈
        triggered = risk_manager.check_take_profit(
            entry_price=100.0,
            current_price=105.0,
            side=OrderSide.BUY,
        )

        assert triggered is False

    def test_check_take_profit_short(self, risk_manager):
        """测试空头止盈"""
        risk_manager.settings.take_profit_percent = 10.0

        # 价格下跌 15%，应该触发止盈
        triggered = risk_manager.check_take_profit(
            entry_price=100.0,
            current_price=85.0,
            side=OrderSide.SELL,
        )

        assert triggered is True

    def test_check_take_profit_disabled(self, risk_manager):
        """测试止盈禁用"""
        risk_manager.settings.take_profit_percent = 0.0

        triggered = risk_manager.check_take_profit(
            entry_price=100.0,
            current_price=200.0,
            side=OrderSide.BUY,
        )

        assert triggered is False

    def test_reset_daily(self, risk_manager):
        """测试重置每日统计"""
        risk_manager.stats.daily_pnl = 100.0
        risk_manager.stats.daily_trades = 10

        risk_manager.reset_daily()

        assert risk_manager.stats.daily_pnl == 0.0
        assert risk_manager.stats.daily_trades == 0

    def test_get_stats(self, risk_manager):
        """测试获取统计"""
        risk_manager.stats.daily_pnl = 50.0
        risk_manager.stats.daily_trades = 3
        risk_manager.stats.total_positions = 1000.0

        stats = risk_manager.get_stats()

        assert stats["daily_pnl"] == 50.0
        assert stats["daily_trades"] == 3
        assert stats["total_positions"] == 1000.0
        assert "limits" in stats
        assert "max_position" in stats["limits"]
        assert "stop_loss_percent" in stats["limits"]
        assert "take_profit_percent" in stats["limits"]

    def test_max_position_reached_tracking(self, risk_manager):
        """测试最大仓位追踪"""
        order1 = Order(
            id="1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=0.1,
            price=50000.0,
            filled=0.1,
        )

        risk_manager.update_position(order1)

        assert risk_manager.stats.max_position_reached == 5000.0

        # 再开一仓
        order2 = Order(
            id="2",
            symbol="ETH/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=1.0,
            price=3000.0,
            filled=1.0,
        )

        risk_manager.update_position(order2)

        # 总仓位应该是 8000
        assert risk_manager.stats.total_positions == 8000.0
        assert risk_manager.stats.max_position_reached == 8000.0
