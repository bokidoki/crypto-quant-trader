"""
数据库管理模块
- SQLite 数据库连接管理
- 数据库初始化和迁移
- 连接池管理
"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
    AsyncEngine,
)
from sqlalchemy.pool import StaticPool


class DatabaseManager:
    """数据库管理器"""

    def __init__(self, db_path: Optional[str] = None):
        """
        初始化数据库管理器

        Args:
            db_path: 数据库文件路径，默认为 data/trader.db
        """
        if db_path is None:
            base_dir = Path(__file__).parent.parent.parent
            db_path = str(base_dir / "data" / "trader.db")

        self.db_url = f"sqlite+aiosqlite:///{db_path}"
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self._initialized = False

    @property
    def engine(self) -> AsyncEngine:
        """获取数据库引擎"""
        if self._engine is None:
            self._engine = create_async_engine(
                self.db_url,
                poolclass=StaticPool,
                echo=False,
            )
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """获取 Session 工厂"""
        if self._session_factory is None:
            self._session_factory = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        return self._session_factory

    async def initialize(self, models: list) -> None:
        """
        初始化数据库，创建所有表

        Args:
            models: 要创建的模型列表
        """
        if self._initialized:
            return

        # 确保数据目录存在
        db_path = Path(self.db_url.replace("sqlite+aiosqlite:///", ""))
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # 导入 Base 并创建所有表
        from .models import Base
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self._initialized = True

    async def close(self) -> None:
        """关闭数据库连接"""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            self._initialized = False

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        获取数据库 Session 上下文管理器

        Yields:
            AsyncSession: 数据库会话
        """
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()


# 全局数据库实例
_db_manager: Optional[DatabaseManager] = None


def get_db_manager(db_path: Optional[str] = None) -> DatabaseManager:
    """获取全局数据库管理器实例"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager(db_path)
    return _db_manager


async def init_database(models: list) -> None:
    """初始化数据库"""
    db_manager = get_db_manager()
    await db_manager.initialize(models)


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话"""
    db_manager = get_db_manager()
    async with db_manager.get_session() as session:
        yield session
