"""
核心交易引擎
"""
import asyncio
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
from enum import Enum

from loguru import logger


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
    
    def __init__(self):
        self.state = EngineState.STOPPED
        self.exchanges: Dict[str, Any] = {}  # 交易所实例
        self.strategies: Dict[str, Any] = {}  # 策略实例
        self.risk_manager = None  # 风控管理器
        self.event_handlers: Dict[str, List[Callable]] = {}  # 事件处理器
        
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
        logger.info(f"交易所已注册: {name}")
    
    def register_strategy(self, name: str, strategy: Any):
        """注册策略"""
        self.strategies[name] = strategy
        logger.info(f"策略已注册: {name}")
    
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
            logger.warning(f"引擎已在运行中: {self.state}")
            return
        
        self.state = EngineState.STARTING
        logger.info("🚀 交易引擎启动中...")
        
        try:
            # 初始化交易所连接
            for name, exchange in self.exchanges.items():
                await exchange.connect()
                logger.info(f"交易所已连接: {name}")
            
            # 初始化策略
            for name, strategy in self.strategies.items():
                await strategy.init()
                logger.info(f"策略已初始化: {name}")
            
            self.state = EngineState.RUNNING
            self.stats["start_time"] = datetime.now()
            
            logger.info("✅ 交易引擎启动成功")
            await self.emit("engine_started")
            
        except Exception as e:
            self.state = EngineState.ERROR
            self.stats["errors"] += 1
            logger.error(f"❌ 引擎启动失败: {e}")
            await self.emit("error", {"type": "startup", "error": str(e)})
    
    async def stop(self):
        """停止引擎"""
        if self.state != EngineState.RUNNING:
            return
        
        self.state = EngineState.STOPPING
        logger.info("🛑 交易引擎停止中...")
        
        try:
            # 停止策略
            for name, strategy in self.strategies.items():
                await strategy.stop()
                logger.info(f"策略已停止: {name}")
            
            # 断开交易所连接
            for name, exchange in self.exchanges.items():
                await exchange.disconnect()
                logger.info(f"交易所已断开: {name}")
            
            self.state = EngineState.STOPPED
            logger.info("✅ 交易引擎已停止")
            await self.emit("engine_stopped")
            
        except Exception as e:
            self.state = EngineState.ERROR
            logger.error(f"❌ 引擎停止失败: {e}")
    
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
        return {
            "state": self.state.value,
            "exchanges": list(self.exchanges.keys()),
            "strategies": list(self.strategies.keys()),
            "stats": self.stats,
            "uptime": str(datetime.now() - self.stats["start_time"]) if self.stats["start_time"] else "N/A",
        }
