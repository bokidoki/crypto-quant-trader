"""
核心交易引擎
"""
import asyncio
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
from enum import Enum

from loguru import logger

from src.openclaw import NotificationManager, TaskScheduler, MessageType


class EngineState(Enum):
    """引擎状态"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class TradingEngine:
    """
    事件驱动的交易引擎

    支持：
    - 多交易所连接
    - 策略调度
    - 风控检查
    - 事件通知
    """

    def __init__(self, notification_manager: Optional[NotificationManager] = None,
                 task_scheduler: Optional[TaskScheduler] = None):
        self.state = EngineState.STOPPED
        self.exchanges: Dict[str, Any] = {}  # 交易所实例
        self.strategies: Dict[str, Any] = {}  # 策略实例
        self.risk_manager = None  # 风控管理器
        self.event_handlers: Dict[str, List[Callable]] = {}  # 事件处理器

        # OpenClaw 集成
        self.notification_manager = notification_manager
        self.task_scheduler = task_scheduler or TaskScheduler()

        # 统计信息
        self.stats = {
            "start_time": None,
            "total_trades": 0,
            "total_pnl": 0.0,
            "errors": 0,
        }

    def register_exchange(self, name: str, exchange: Any):
        """注册交易所"""
        self.exchanges[name] = exchange
        logger.info(f"交易所已注册：{name}")

    def register_strategy(self, name: str, strategy: Any):
        """注册策略"""
        self.strategies[name] = strategy
        logger.info(f"策略已注册：{name}")

    def add_strategy(self, name: str, strategy: Any):
        """添加策略（别名）"""
        self.register_strategy(name, strategy)

    def set_risk_manager(self, risk_manager: Any):
        """设置风控管理器"""
        self.risk_manager = risk_manager
        logger.info("风控管理器已设置")

    def on(self, event: str, handler: Callable):
        """注册事件处理器"""
        if event not in self.event_handlers:
            self.event_handlers[event] = []
        self.event_handlers[event].append(handler)

    async def emit(self, event: str, data: Any = None):
        """触发事件"""
        if event in self.event_handlers:
            for handler in self.event_handlers[event]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(data)
                    else:
                        handler(data)
                except Exception as e:
                    logger.error(f"事件处理器错误 [{event}]: {e}")

    async def start(self):
        """启动引擎"""
        if self.state != EngineState.STOPPED:
            logger.warning(f"引擎已在运行中：{self.state}")
            return

        self.state = EngineState.STARTING
        logger.info("交易引擎启动中...")

        try:
            # 初始化交易所连接（跳过已连接的）
            for name, exchange in self.exchanges.items():
                if hasattr(exchange, 'connected') and not exchange.connected:
                    await exchange.connect()
                    logger.info(f"交易所已连接：{name}")
                elif hasattr(exchange, 'connected') and exchange.connected:
                    logger.info(f"交易所已连接（跳过）：{name}")

            # 初始化策略
            for name, strategy in self.strategies.items():
                await strategy.init()
                logger.info(f"策略已初始化：{name}")

            # 启动策略
            for name, strategy in self.strategies.items():
                if hasattr(strategy, 'start'):
                    await strategy.start(self)
                    logger.info(f"策略已启动：{name}")

            self.state = EngineState.RUNNING
            self.stats["start_time"] = datetime.now()

            logger.info("✅ 交易引擎启动成功")
            await self.emit("engine_started")

            # 发送系统通知
            await self._notify_system("引擎启动", "交易引擎已成功启动并开始运行")

            # 启动任务调度器
            if self.task_scheduler:
                await self.task_scheduler.start()

            # 启动策略调度循环（新增）
            self._scheduler_task = asyncio.create_task(self._run_scheduler())

        except Exception as e:
            self.state = EngineState.ERROR
            self.stats["errors"] += 1
            logger.error(f"❌ 引擎启动失败：{e}")
            await self.emit("error", {"type": "startup", "error": str(e)})
            await self._notify_error("引擎启动失败", str(e))

    async def stop(self):
        """停止引擎"""
        if self.state != EngineState.RUNNING:
            return

        self.state = EngineState.STOPPING
        logger.info("交易引擎停止中...")

        try:
            # 停止策略调度循环
            if hasattr(self, '_scheduler_task') and not self._scheduler_task.done():
                self._scheduler_task.cancel()
                try:
                    await self._scheduler_task
                except asyncio.CancelledError:
                    pass
                logger.info("策略调度循环已停止")

            # 停止策略
            for name, strategy in self.strategies.items():
                if hasattr(strategy, 'stop'):
                    await strategy.stop()
                    logger.info(f"策略已停止：{name}")

            # 断开交易所连接（只断开已连接的）
            for name, exchange in self.exchanges.items():
                if hasattr(exchange, 'connected') and exchange.connected:
                    await exchange.disconnect()
                    logger.info(f"交易所已断开：{name}")

            self.state = EngineState.STOPPED
            self.stats["start_time"] = None  # 清空启动时间，停止时运行时间应归零
            logger.info("✅ 交易引擎已停止")
            await self.emit("engine_stopped")

            # 发送系统通知
            await self._notify_system("引擎停止", "交易引擎已正常停止")

            # 停止任务调度器
            if self.task_scheduler:
                await self.task_scheduler.stop()

        except Exception as e:
            self.state = EngineState.ERROR
            logger.error(f"❌ 引擎停止失败：{e}")
            await self._notify_error("引擎停止失败", str(e))

    async def _run_scheduler(self):
        """
        策略调度循环（新增）
        持续获取行情并调用策略，生成信号后执行
        """
        logger.info("策略调度循环已启动")

        while self.state == EngineState.RUNNING:
            try:
                # 遍历所有策略
                for name, strategy in self.strategies.items():
                    try:
                        # 获取最新行情
                        if strategy.exchange and strategy.symbol:
                            ticker_data = await strategy.exchange.get_ticker(strategy.symbol)
                            if ticker_data:
                                # 更新策略行情
                                await strategy.on_tick(ticker_data)

                                # 生成交易信号
                                signal = await strategy.generate_signal()

                                # 执行信号
                                if signal:
                                    await self._execute_signal(signal, strategy)
                    except Exception as e:
                        logger.error(f"策略 [{name}] 执行错误：{e}")
                        self.stats["errors"] += 1

                # 每秒检查一次
                await asyncio.sleep(1)

            except asyncio.CancelledError:
                logger.info("策略调度循环收到取消信号")
                break
            except Exception as e:
                logger.error(f"调度循环错误：{e}")
                await asyncio.sleep(5)  # 错误后等待 5 秒继续

    async def _execute_signal(self, signal: Dict, strategy):
        """
        执行交易信号（新增）

        Args:
            signal: 信号字典，包含 side, amount, reason 等
            strategy: 策略实例
        """
        try:
            # 风控检查
            if self.risk_manager:
                from src.exchanges.base import OrderSide, Order, OrderType
                mock_order = Order(
                    id=f"mock_{datetime.now().timestamp()}",
                    symbol=strategy.symbol,
                    side=OrderSide.BUY if signal.get("side") == "buy" else OrderSide.SELL,
                    type=OrderType.MARKET,
                    amount=signal.get("amount", 0),
                    price=signal.get("price", 0),
                )
                passed, reason = self.risk_manager.check_order(mock_order)
                if not passed:
                    logger.warning(f"风控拦截：{reason}")
                    await self._notify_risk("订单被风控拦截", reason)
                    return

            # 执行下单
            if signal.get("side") == "buy":
                order = await strategy.buy(
                    amount=signal.get("amount", 0),
                    price=signal.get("price"),
                )
            else:
                order = await strategy.sell(
                    amount=signal.get("amount", 0),
                    price=signal.get("price"),
                )

            if order:
                logger.info(f"订单执行成功：{order.id} {order.side.value} {order.amount} {order.symbol}")

                # 发送到风控更新持仓
                if self.risk_manager:
                    self.risk_manager.update_position(order)

                # 发送交易通知
                await self._notify_trade(
                    action="buy" if order.side == OrderSide.BUY else "sell",
                    symbol=order.symbol,
                    price=order.price or 0,
                    quantity=order.amount,
                    order_id=order.id,
                )

        except Exception as e:
            logger.error(f"信号执行失败：{e}")
            self.stats["errors"] += 1

    async def run_forever(self):
        """持续运行"""
        await self.start()

        try:
            while self.state == EngineState.RUNNING:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("收到取消信号")
        finally:
            await self.stop()

    def get_status(self) -> Dict:
        """获取引擎状态"""
        if self.stats.get("start_time"):
            delta = datetime.now() - self.stats["start_time"]
            total_seconds = int(delta.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            uptime = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            uptime = "00:00:00"

        # 获取交易所连接状态
        exchanges_status = {}
        for name, exchange in self.exchanges.items():
            connected = getattr(exchange, 'connected', False)
            exchanges_status[name] = {
                'connected': connected,
                'status': 'connected' if connected else 'disconnected'
            }

        return {
            "state": self.state.value,
            "exchanges": exchanges_status,
            "strategies": list(self.strategies.keys()),
            "stats": self.stats,
            "uptime": uptime,
        }

    # ==================== OpenClaw 通知钩子 ====================

    async def _notify_system(self, event: str, detail: str):
        """发送系统状态通知"""
        if self.notification_manager:
            content = self.notification_manager.format_system_msg(event, detail)
            await self.notification_manager.send_async(MessageType.SYSTEM, content)

    async def _notify_error(self, error_type: str, detail: str):
        """发送错误告警"""
        if self.notification_manager:
            content = f"类型：{error_type}\n详情：{detail}"
            await self.notification_manager.send_async(MessageType.ERROR, content)

    async def _notify_trade(self, action: str, symbol: str, price: float,
                            quantity: float, order_id: str = ""):
        """发送交易通知"""
        if self.notification_manager:
            content = self.notification_manager.format_order_msg(
                action, symbol, price, quantity, order_id
            )
            await self.notification_manager.send_async(MessageType.TRADE, content)

    async def _notify_risk(self, risk_type: str, detail: str, value: Any = None):
        """发送风控告警"""
        if self.notification_manager:
            content = self.notification_manager.format_risk_msg(risk_type, detail, value)
            await self.notification_manager.send_async(MessageType.RISK, content)
