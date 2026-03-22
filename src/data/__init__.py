"""
数据存储模块

提供加密货币量化交易系统的数据存储功能：
- 数据库管理（SQLite + SQLAlchemy 异步操作）
- 数据模型（订单、K 线、交易、持仓、策略）
- 数据访问层（CRUD 操作）
"""

from .database import (
    DatabaseManager,
    get_db_manager,
    init_database,
    get_db_session,
)

from .models import (
    Base,
    OrderModel,
    KLineModel,
    TradeModel,
    PositionModel,
    StrategyModel,
)

from .repository import (
    BaseRepository,
    OrderRepository,
    KLineRepository,
    TradeRepository,
    PositionRepository,
    StrategyRepository,
)

__all__ = [
    # 数据库管理
    "DatabaseManager",
    "get_db_manager",
    "init_database",
    "get_db_session",
    # 数据模型
    "Base",
    "OrderModel",
    "KLineModel",
    "TradeModel",
    "PositionModel",
    "StrategyModel",
    # 数据访问层
    "BaseRepository",
    "OrderRepository",
    "KLineRepository",
    "TradeRepository",
    "PositionRepository",
    "StrategyRepository",
]
