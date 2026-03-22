"""
通知管理器 - 飞书消息推送

支持：
- 交易通知（订单成交、撤单等）
- 风控告警（止损触发、仓位超限等）
- 系统状态（引擎启停、错误告警等）
"""
import asyncio
import subprocess
from enum import Enum
from typing import Optional, Dict, Any
from pathlib import Path

from loguru import logger


class MessageType(Enum):
    """消息类型"""
    TRADE = "trade"           # 交易通知
    RISK = "risk"             # 风控告警
    SYSTEM = "system"         # 系统状态
    ERROR = "error"           # 错误告警


class NotificationManager:
    """
    通知管理器

    通过调用外部脚本发送飞书消息
    """

    def __init__(self, script_path: Optional[str] = None, enabled: bool = True):
        """
        初始化通知管理器

        Args:
            script_path: 飞书发送脚本路径，默认使用 D:\\workflow\\scripts\\feishu-send.js
            enabled: 是否启用通知
        """
        self.enabled = enabled
        self.script_path = script_path or r"D:\workflow\scripts\feishu-send.js"
        self.receive_id: Optional[str] = None  # 可选的指定接收者

        # 消息前缀（用于区分类型）
        self.prefix_map = {
            MessageType.TRADE: "📈【交易通知】",
            MessageType.RISK: "⚠️【风控告警】",
            MessageType.SYSTEM: "🔧【系统状态】",
            MessageType.ERROR: "❌【错误告警】",
        }

    def send(self, msg_type: MessageType, content: str, receive_id: Optional[str] = None) -> bool:
        """
        发送通知（同步）

        Args:
            msg_type: 消息类型
            content: 消息内容
            receive_id: 可选的指定接收者 open_id

        Returns:
            是否发送成功
        """
        if not self.enabled:
            logger.debug(f"通知已禁用，跳过发送：{content}")
            return False

        try:
            prefix = self.prefix_map.get(msg_type, "")
            full_content = f"{prefix}\n\n{content}"

            # 构建命令
            cmd = ["node", self.script_path, full_content]
            if receive_id:
                cmd.append(receive_id)
            elif self.receive_id:
                cmd.append(self.receive_id)

            # 异步执行脚本
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                logger.info(f"通知发送成功：{msg_type.value}")
                return True
            else:
                logger.error(f"通知发送失败：{result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("通知发送超时")
            return False
        except Exception as e:
            logger.error(f"通知发送异常：{e}")
            return False

    async def send_async(self, msg_type: MessageType, content: str, receive_id: Optional[str] = None) -> bool:
        """
        发送通知（异步）

        Args:
            msg_type: 消息类型
            content: 消息内容
            receive_id: 可选的指定接收者 open_id

        Returns:
            是否发送成功
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.send(msg_type, content, receive_id)
        )

    # ==================== 便捷方法 ====================

    def send_trade(self, content: str, **kwargs) -> bool:
        """发送交易通知"""
        return self.send(MessageType.TRADE, content, **kwargs)

    def send_risk(self, content: str, **kwargs) -> bool:
        """发送风控告警"""
        return self.send(MessageType.RISK, content, **kwargs)

    def send_system(self, content: str, **kwargs) -> bool:
        """发送系统状态"""
        return self.send(MessageType.SYSTEM, content, **kwargs)

    def send_error(self, content: str, **kwargs) -> bool:
        """发送错误告警"""
        return self.send(MessageType.ERROR, content, **kwargs)

    # ==================== 格式化消息 ====================

    @staticmethod
    def format_order_msg(action: str, symbol: str, price: float,
                         quantity: float, order_id: str = "") -> str:
        """
        格式化订单消息

        Args:
            action: 操作（买入/卖出/撤单）
            symbol: 交易对
            price: 价格
            quantity: 数量
            order_id: 订单 ID

        Returns:
            格式化后的消息
        """
        msg = f"操作：{action}\n"
        msg += f"交易对：{symbol}\n"
        msg += f"价格：{price}\n"
        msg += f"数量：{quantity}"
        if order_id:
            msg += f"\n订单 ID: {order_id}"
        return msg

    @staticmethod
    def format_risk_msg(risk_type: str, detail: str, value: Any = None) -> str:
        """
        格式化风控消息

        Args:
            risk_type: 风控类型
            detail: 详细信息
            value: 相关数值

        Returns:
            格式化后的消息
        """
        msg = f"类型：{risk_type}\n"
        msg += f"详情：{detail}"
        if value is not None:
            msg += f"\n数值：{value}"
        return msg

    @staticmethod
    def format_system_msg(event: str, detail: str = "") -> str:
        """
        格式化系统消息

        Args:
            event: 事件名称
            detail: 详细信息

        Returns:
            格式化后的消息
        """
        msg = f"事件：{event}"
        if detail:
            msg += f"\n详情：{detail}"
        return msg
