"""
策略基类
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field

from loguru import logger

from ..exchanges.base import Order, OrderSide, OrderType, OrderStatus, Ticker, KLine


@dataclass
class StrategyConfig:
    """策略配置"""
    name: str
    symbol: str
    timeframe: str = "1h"
    enabled: bool = True

    # 仓位设置
    position_size: float = 0.01  # 仓位大小（基础货币数量）
    max_positions: int = 1  # 最大持仓数

    # 止损止盈
    stop_loss: Optional[float] = None  # 止损比例，如 0.05 表示 5%
    take_profit: Optional[float] = None  # 止盈比例

    # 自定义参数
    params: Dict = field(default_factory=dict)


class BaseStrategy(ABC):
    """
    策略基类

    所有交易策略必须继承此类并实现以下方法：
    - on_tick: 行情更新时调用
    - on_bar: K 线更新时调用
    - generate_signal: 生成交易信号
    """

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.name = config.name
        self.symbol = config.symbol
        self.timeframe = config.timeframe

        # 交易所引用（由引擎设置）
        self.exchange = None

        # 数据存储
        self.bars: List[KLine] = []
        self.ticker: Optional[Ticker] = None
        self.positions: List[Order] = []

        # 统计
        self.stats = {
            "total_trades": 0,
            "win_trades": 0,
            "loss_trades": 0,
            "total_pnl": 0.0,
            "max_drawdown": 0.0,
        }

    async def init(self):
        """
        初始化策略

        子类可以覆盖此方法进行自定义初始化
        """
        logger.info(f"策略初始化：{self.name}")

        # 加载历史 K 线
        if self.exchange:
            self.bars = await self.exchange.get_klines(
                self.symbol, self.timeframe, limit=200
            )
            logger.info(f"已加载 {len(self.bars)} 根 K 线")

    async def stop(self):
        """停止策略"""
        logger.info(f"策略停止：{self.name}")

    @abstractmethod
    async def on_tick(self, ticker: Ticker):
        """
        行情更新回调

        Args:
            ticker: 最新行情
        """
        pass

    @abstractmethod
    async def on_bar(self, bar: KLine):
        """
        K 线更新回调

        Args:
            bar: 最新 K 线
        """
        pass

    @abstractmethod
    async def generate_signal(self) -> Optional[Dict]:
        """
        生成交易信号

        Returns:
            信号字典，包含 side, amount, price 等，或 None 表示无信号
        """
        pass

    async def buy(self, amount: float, price: Optional[float] = None) -> Optional[Order]:
        """
        下买单

        Args:
            amount: 数量
            price: 价格（None 为市价单）

        Returns:
            订单的对象
        """
        if not self.exchange:
            logger.error("交易所未设置")
            return None

        order_type = OrderType.LIMIT if price else OrderType.MARKET

        try:
            order = await self.exchange.create_order(
                symbol=self.symbol,
                side=OrderSide.BUY,
                order_type=order_type,
                amount=amount,
                price=price,
            )
            self.positions.append(order)
            self.stats["total_trades"] += 1
            logger.info(f"买入订单：{order.id} {amount} {self.symbol}")
            return order
        except Exception as e:
            logger.error(f"买入失败：{e}")
            return None

    async def sell(self, amount: float, price: Optional[float] = None) -> Optional[Order]:
        """
        下卖单

        Args:
            amount: 数量
            price: 价格（None 为市价单）

        Returns:
            订单的对象
        """
        if not self.exchange:
            logger.error("交易所未设置")
            return None

        order_type = OrderType.LIMIT if price else OrderType.MARKET

        try:
            order = await self.exchange.create_order(
                symbol=self.symbol,
                side=OrderSide.SELL,
                order_type=order_type,
                amount=amount,
                price=price,
            )
            logger.info(f"卖出订单：{order.id} {amount} {self.symbol}")
            return order
        except Exception as e:
            logger.error(f"卖出失败：{e}")
            return None

    async def close_position(self, order_id: Optional[str] = None, percentage: float = 1.0):
        """
        平仓

        Args:
            order_id: 指定订单 ID，None 表示平掉所有仓位
            percentage: 平仓比例，1.0 表示 100% 平仓

        Returns:
            平仓订单列表
        """
        if not self.positions:
            logger.info("无持仓可平")
            return []

        closed_orders = []

        # 如果指定了 order_id，只平指定订单
        if order_id:
            for pos in self.positions:
                if pos.id == order_id and pos.status == OrderStatus.OPEN:
                    # 计算平仓数量
                    close_amount = pos.filled * percentage
                    if close_amount <= 0:
                        logger.info(f"订单 {order_id} 无持仓可平")
                        continue

                    # 反向平仓
                    close_side = OrderSide.SELL if pos.side == OrderSide.BUY else OrderSide.BUY

                    try:
                        close_order = await self.exchange.create_order(
                            symbol=self.symbol,
                            side=close_side,
                            order_type=OrderType.MARKET,
                            amount=close_amount,
                        )
                        closed_orders.append(close_order)
                        self.stats["total_trades"] += 1

                        # 更新原订单状态
                        pos.remaining -= close_amount
                        if pos.remaining <= 0:
                            pos.status = OrderStatus.CLOSED

                        logger.info(f"平仓成功：{close_order.id} {close_amount} {self.symbol}")

                        # 计算盈亏
                        pnl = self._calculate_pnl(pos, close_amount)
                        self.stats["total_pnl"] += pnl

                        if pnl > 0:
                            self.stats["win_trades"] += 1
                        else:
                            self.stats["loss_trades"] += 1

                    except Exception as e:
                        logger.error(f"平仓失败：{e}")
                    break
        else:
            # 平掉所有仓位
            for pos in self.positions:
                if pos.status != OrderStatus.OPEN or pos.filled <= 0:
                    continue

                # 计算平仓数量
                close_amount = pos.filled * percentage
                if close_amount <= 0:
                    continue

                # 反向平仓
                close_side = OrderSide.SELL if pos.side == OrderSide.BUY else OrderSide.BUY

                try:
                    close_order = await self.exchange.create_order(
                        symbol=self.symbol,
                        side=close_side,
                        order_type=OrderType.MARKET,
                        amount=close_amount,
                    )
                    closed_orders.append(close_order)
                    self.stats["total_trades"] += 1

                    # 更新原订单状态
                    pos.remaining -= close_amount
                    if pos.remaining <= 0:
                        pos.status = OrderStatus.CLOSED

                    logger.info(f"平仓成功：{close_order.id} {close_amount} {self.symbol}")

                    # 计算盈亏
                    pnl = self._calculate_pnl(pos, close_amount)
                    self.stats["total_pnl"] += pnl

                    if pnl > 0:
                        self.stats["win_trades"] += 1
                    else:
                        self.stats["loss_trades"] += 1

                except Exception as e:
                    logger.error(f"平仓失败：{e}")

        # 清理已完成的仓位
        self.positions = [p for p in self.positions if p.status == OrderStatus.OPEN and p.remaining > 0]

        return closed_orders

    def _calculate_pnl(self, order: Order, close_amount: float) -> float:
        """
        计算盈亏

        Args:
            order: 原始订单
            close_amount: 平仓数量

        Returns:
            盈亏金额 (USDT)
        """
        if not self.ticker:
            return 0.0

        current_price = self.ticker.last
        entry_price = order.price or 0

        if entry_price <= 0:
            return 0.0

        if order.side == OrderSide.BUY:
            # 多头盈亏 = (当前价 - 入场价) * 数量
            pnl = (current_price - entry_price) * close_amount
        else:
            # 空头盈亏 = (入场价 - 当前价) * 数量
            pnl = (entry_price - current_price) * close_amount

        return pnl

    def update_bar(self, bar: KLine):
        """更新 K 线数据"""
        self.bars.append(bar)

        # 保持最多 500 根 K 线
        if len(self.bars) > 500:
            self.bars = self.bars[-500:]

    def update_ticker(self, ticker: Ticker):
        """更新行情数据"""
        self.ticker = ticker

        # 检查止损止盈
        if self.positions:
            self._check_stop_loss_take_profit()

    def _check_stop_loss_take_profit(self):
        """检查止损止盈条件"""
        if not self.ticker or not self.positions:
            return

        current_price = self.ticker.last

        for pos in self.positions:
            if pos.status != OrderStatus.OPEN:
                continue

            entry_price = pos.price or pos.entry_price
            if entry_price <= 0:
                continue

            # 计算盈亏比例
            if pos.side == OrderSide.BUY:
                pnl_percent = (current_price - entry_price) / entry_price
            else:
                pnl_percent = (entry_price - current_price) / entry_price

            # 检查止损
            if self.config.stop_loss and pnl_percent <= -self.config.stop_loss:
                logger.warning(f"触发止损：{self.symbol} 盈亏 {pnl_percent*100:.2f}%")
                # 这里可以自动触发平仓，但为了避免循环调用，由外部处理

            # 检查止盈
            if self.config.take_profit and pnl_percent >= self.config.take_profit:
                logger.info(f"触发止盈：{self.symbol} 盈亏 {pnl_percent*100:.2f}%")

    def get_stats(self) -> Dict:
        """获取策略统计"""
        win_rate = 0
        if self.stats["total_trades"] > 0:
            win_rate = self.stats["win_trades"] / self.stats["total_trades"] * 100

        return {
            "name": self.name,
            "symbol": self.symbol,
            "total_trades": self.stats["total_trades"],
            "win_rate": f"{win_rate:.2f}%",
            "total_pnl": self.stats["total_pnl"],
            "max_drawdown": self.stats["max_drawdown"],
        }
