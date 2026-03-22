"""
定时任务调度器

支持：
- Cron 表达式调度
- 间隔调度
- 一次性任务
"""
import asyncio
from datetime import datetime, timedelta
from typing import Callable, Any, Optional, Dict, List, Union
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger


class TaskState(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ScheduledTask:
    """定时任务"""
    name: str
    handler: Callable
    cron_expr: Optional[str] = None  # Cron 表达式（简单版：分 时 日 月 周）
    interval: Optional[float] = None  # 间隔（秒）
    run_at: Optional[datetime] = None  # 一次性执行时间
    enabled: bool = True
    state: TaskState = TaskState.PENDING
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    error_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class TaskScheduler:
    """
    定时任务调度器

    支持：
    - Cron 表达式（简化版）
    - 固定间隔
    - 一次性任务
    """

    def __init__(self):
        self.tasks: Dict[str, ScheduledTask] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    def add_cron(self, name: str, handler: Callable, cron_expr: str,
                 enabled: bool = True, **metadata) -> ScheduledTask:
        """
        添加 Cron 任务

        Args:
            name: 任务名称
            handler: 处理函数（可以是同步或异步）
            cron_expr: Cron 表达式（分 时 日 月 周），如 "*/5 * * * *" 表示每 5 分钟
            enabled: 是否启用
            **metadata: 额外元数据

        Returns:
            ScheduledTask 对象
        """
        task = ScheduledTask(
            name=name,
            handler=handler,
            cron_expr=cron_expr,
            enabled=enabled,
            metadata=metadata,
            next_run=self._calc_next_cron(cron_expr),
        )
        self.tasks[name] = task
        logger.info(f"添加 Cron 任务：{name} ({cron_expr})")
        return task

    def add_interval(self, name: str, handler: Callable, interval: float,
                     enabled: bool = True, **metadata) -> ScheduledTask:
        """
        添加间隔任务

        Args:
            name: 任务名称
            handler: 处理函数
            interval: 间隔时间（秒）
            enabled: 是否启用
            **metadata: 额外元数据

        Returns:
            ScheduledTask 对象
        """
        task = ScheduledTask(
            name=name,
            handler=handler,
            interval=interval,
            enabled=enabled,
            metadata=metadata,
            next_run=datetime.now() + timedelta(seconds=interval),
        )
        self.tasks[name] = task
        logger.info(f"添加间隔任务：{name} (每{interval}秒)")
        return task

    def add_once(self, name: str, handler: Callable, run_at: datetime,
                 **metadata) -> ScheduledTask:
        """
        添加一次性任务

        Args:
            name: 任务名称
            handler: 处理函数
            run_at: 执行时间
            **metadata: 额外元数据

        Returns:
            ScheduledTask 对象
        """
        task = ScheduledTask(
            name=name,
            handler=handler,
            run_at=run_at,
            enabled=True,
            metadata=metadata,
            next_run=run_at,
        )
        self.tasks[name] = task
        logger.info(f"添加一次性任务：{name} ({run_at})")
        return task

    def remove(self, name: str) -> bool:
        """移除任务"""
        if name in self.tasks:
            del self.tasks[name]
            logger.info(f"移除任务：{name}")
            return True
        return False

    def enable(self, name: str) -> bool:
        """启用任务"""
        if name in self.tasks:
            self.tasks[name].enabled = True
            logger.info(f"启用任务：{name}")
            return True
        return False

    def disable(self, name: str) -> bool:
        """禁用任务"""
        if name in self.tasks:
            self.tasks[name].enabled = False
            logger.info(f"禁用任务：{name}")
            return True
        return False

    async def start(self):
        """启动调度器"""
        if self._running:
            logger.warning("调度器已在运行中")
            return

        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("⏰ 任务调度器已启动")

    async def stop(self):
        """停止调度器"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("⏹️ 任务调度器已停止")

    async def _run(self):
        """调度器主循环"""
        while self._running:
            try:
                await self._check_and_run()
                await asyncio.sleep(1)  # 每秒检查一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"调度器错误：{e}")
                await asyncio.sleep(5)

    async def _check_and_run(self):
        """检查并执行到期的任务"""
        now = datetime.now()

        async with self._lock:
            for name, task in self.tasks.items():
                if not task.enabled:
                    continue

                if task.next_run and task.next_run <= now:
                    await self._execute_task(task)
                    self._update_next_run(task)

    async def _execute_task(self, task: ScheduledTask):
        """执行任务"""
        task.state = TaskState.RUNNING
        task.last_run = datetime.now()

        try:
            if asyncio.iscoroutinefunction(task.handler):
                await task.handler()
            else:
                task.handler()
            task.state = TaskState.COMPLETED
            task.run_count += 1
            logger.debug(f"任务执行成功：{task.name}")
        except asyncio.CancelledError:
            task.state = TaskState.CANCELLED
            raise
        except Exception as e:
            task.state = TaskState.FAILED
            task.error_count += 1
            logger.error(f"任务执行失败 [{task.name}]: {e}")

    def _update_next_run(self, task: ScheduledTask):
        """更新下次执行时间"""
        now = datetime.now()

        if task.cron_expr:
            task.next_run = self._calc_next_cron(task.cron_expr)
        elif task.interval:
            task.next_run = now + timedelta(seconds=task.interval)
        elif task.run_at:
            # 一次性任务，执行后禁用
            task.enabled = False
            task.next_run = None
        else:
            task.next_run = None

    def _calc_next_cron(self, cron_expr: str) -> datetime:
        """
        计算 Cron 表达式的下次执行时间（简化版）

        支持格式：分 时 日 月 周
        支持：* (任意), */N (每 N)
        """
        parts = cron_expr.split()
        if len(parts) != 5:
            raise ValueError(f"无效的 Cron 表达式：{cron_expr}")

        minute, hour, day, month, weekday = parts

        now = datetime.now()
        candidate = now.replace(second=0, microsecond=0)

        # 简单处理：只支持 */N 和 *
        for _ in range(366 * 24 * 60):  # 最多查找一年
            candidate += timedelta(minutes=1)

            if not self._match_field(candidate.minute, minute):
                continue
            if not self._match_field(candidate.hour, hour):
                continue
            if not self._match_field(candidate.day, day):
                continue
            if not self._match_field(candidate.month, month):
                continue
            if not self._match_field(candidate.weekday() + 1, weekday):  # 周一=1
                continue

            return candidate

        raise ValueError(f"无法计算 Cron 表达式的下次执行时间：{cron_expr}")

    def _match_field(self, value: int, field: str) -> bool:
        """匹配单个字段"""
        if field == "*":
            return True
        if field.startswith("*/"):
            step = int(field[2:])
            return value % step == 0
        if field.isdigit():
            return value == int(field)
        if "," in field:
            values = [int(x.strip()) for x in field.split(",")]
            return value in values
        if "-" in field:
            start, end = field.split("-")
            return int(start) <= value <= int(end)
        return False

    def get_status(self) -> Dict[str, Any]:
        """获取调度器状态"""
        return {
            "running": self._running,
            "task_count": len(self.tasks),
            "tasks": {
                name: {
                    "enabled": task.enabled,
                    "state": task.state.value,
                    "cron_expr": task.cron_expr,
                    "interval": task.interval,
                    "last_run": task.last_run.isoformat() if task.last_run else None,
                    "next_run": task.next_run.isoformat() if task.next_run else None,
                    "run_count": task.run_count,
                    "error_count": task.error_count,
                }
                for name, task in self.tasks.items()
            }
        }
