"""
网格交易策略

自动在价格区间内挂单，低买高卖赚取差价
"""
from typing import Dict, List, Optional
from datetime import datetime
from decimal import Decimal
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger


class GridStatus(str, Enum):
    """网格状态"""
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"


@dataclass
class GridLevel:
    """网格档位"""
    level: int           # 档位编号
    price: Decimal       # 价格
    amount: Decimal      # 数量
    side: str            # buy/sell
    order_id: Optional[str] = None  # 订单 ID
    filled: Decimal = Decimal("0")  # 已成交
    is_active: bool = True  # 是否有效


@dataclass
class GridTrading:
    """
    网格交易实例

    参数:
        id: 网格 ID
        symbol: 交易对
        lower_price: 价格下限
        upper_price: 价格上限
        grid_num: 网格数量
        total_amount: 总金额
    """
    id: str
    symbol: str
    lower_price: Decimal       # 价格下限
    upper_price: Decimal       # 价格上限
    grid_num: int              # 网格数量
    total_amount: Decimal      # 总金额

    # 计算得出
    grid_spacing: Decimal = field(default=Decimal("0"))  # 网格间距
    grid_prices: List[Decimal] = field(default_factory=list)  # 网格价格
    levels: Dict[int, GridLevel] = field(default_factory=dict)  # 网格档位

    # 状态
    status: GridStatus = GridStatus.RUNNING
    current_price: Decimal = field(default=Decimal("0"))
    profit: Decimal = Decimal("0")  # 已实现利润

    # 统计
    buy_count: int = 0
    sell_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_trade_at: Optional[datetime] = None

    def __post_init__(self):
        """初始化后计算网格"""
        if self.grid_num > 0 and self.lower_price < self.upper_price:
            self._calculate_grids()

    def _calculate_grids(self):
        """计算网格价格"""
        # 网格间距
        self.grid_spacing = (self.upper_price - self.lower_price) / self.grid_num

        # 计算每个网格的价格
        self.grid_prices = []
        for i in range(self.grid_num + 1):
            price = self.lower_price + self.grid_spacing * i
            self.grid_prices.append(price)

        # 初始化网格档位
        self.levels = {}
        for i, price in enumerate(self.grid_prices):
            # 中间价以下的挂买单，以上的挂卖单
            mid_index = len(self.grid_prices) // 2

            if i < mid_index:
                side = "buy"
            else:
                side = "sell"

            # 每档金额
            amount_per_grid = self.total_amount / self.grid_num / price

            self.levels[i] = GridLevel(
                level=i,
                price=price,
                amount=amount_per_grid,
                side=side,
            )

    def update_price(self, current_price: Decimal):
        """
        更新当前价格，检查是否需要交易

        Args:
            current_price: 当前价格
        """
        self.current_price = current_price

        # 检查是否有网格被触发
        for level_idx, level in self.levels.items():
            if not level.is_active:
                continue

            # 检查买单：价格低于网格价
            if level.side == "buy" and current_price <= level.price:
                if level.order_id is None or level.filled > 0:
                    # 需要挂买单或重新挂单
                    pass  # 由外部处理

            # 检查卖单：价格高于网格价
            elif level.side == "sell" and current_price >= level.price:
                if level.order_id is None or level.filled > 0:
                    # 需要挂卖单或重新挂单
                    pass  # 由外部处理

    def get_inactive_grids(self) -> List[GridLevel]:
        """获取需要重新挂单的档位"""
        inactive = []
        for level in self.levels.values():
            if level.is_active and level.order_id is None:
                inactive.append(level)
        return inactive

    def get_active_order_ids(self) -> List[str]:
        """获取所有活动订单 ID"""
        return [
            level.order_id
            for level in self.levels.values()
            if level.order_id and level.is_active
        ]

    def mark_level_filled(self, level_idx: int, filled_amount: Decimal):
        """标记档位已成交"""
        if level_idx not in self.levels:
            return

        level = self.levels[level_idx]
        level.filled = filled_amount
        self.last_trade_at = datetime.now()

        # 统计
        if level.side == "buy":
            self.buy_count += 1
        else:
            self.sell_count += 1

        # 计算利润（简化）
        if level.side == "sell" and filled_amount > 0:
            # 卖单成交，计算利润
            profit_price = level.price - self.grid_prices[level_idx - 1] if level_idx > 0 else Decimal("0")
            self.profit += profit_price * filled_amount


class GridTradingEngine:
    """
    网格交易引擎

    功能:
    - 创建网格交易
    - 监控价格并自动挂单
    - 自动撤单重挂
    - 统计网格利润
    """

    def __init__(self, order_manager=None, price_feed=None):
        """
        初始化网格交易引擎

        Args:
            order_manager: 订单管理器
            price_feed: 价格源
        """
        self.order_manager = order_manager
        self.price_feed = price_feed
        self._grids: Dict[str, GridTrading] = {}

    def create_grid(
        self,
        symbol: str,
        lower_price: float,
        upper_price: float,
        grid_num: int,
        total_amount: float,
    ) -> GridTrading:
        """
        创建网格交易

        Args:
            symbol: 交易对
            lower_price: 价格下限
            upper_price: 价格上限
            grid_num: 网格数量
            total_amount: 总金额（USDT）

        Returns:
            网格交易对象
        """
        import uuid

        grid = GridTrading(
            id=str(uuid.uuid4())[:8],
            symbol=symbol,
            lower_price=Decimal(str(lower_price)),
            upper_price=Decimal(str(upper_price)),
            grid_num=grid_num,
            total_amount=Decimal(str(total_amount)),
        )

        self._grids[grid.id] = grid
        logger.info(
            f"创建网格交易：{grid.id} {symbol} "
            f"[{lower_price}-{upper_price}] {grid_num}格 {total_amount}USDT"
        )

        return grid

    async def update_grid_price(self, grid_id: str, current_price: float):
        """
        更新网格价格并执行交易

        Args:
            grid_id: 网格 ID
            current_price: 当前价格
        """
        grid = self._grids.get(grid_id)
        if not grid or grid.status != GridStatus.RUNNING:
            return

        current_price_decimal = Decimal(str(current_price))
        grid.update_price(current_price_decimal)

        # 检查需要挂单的档位
        for level_idx, level in grid.levels.items():
            if not level.is_active:
                continue

            # 检查是否需要挂单
            should_place_order = False

            if level.side == "buy" and current_price_decimal <= level.price:
                # 价格低于网格价，挂买单
                if level.order_id is None:
                    should_place_order = True

            elif level.side == "sell" and current_price_decimal >= level.price:
                # 价格高于网格价，挂卖单
                if level.order_id is None:
                    should_place_order = True

            if should_place_order and self.order_manager:
                order = self.order_manager.create_order(
                    symbol=grid.symbol,
                    side=level.side,
                    amount=float(level.amount),
                    order_type="limit",
                    price=float(level.price),
                )

                success = await self.order_manager.submit_order(order)

                if success:
                    level.order_id = order.id
                    logger.debug(f"网格挂单：{grid.id} {level.side} {level.amount} @ {level.price}")

    async def on_order_filled(self, order_id: str, filled_amount: float):
        """
        订单成交回调

        Args:
            order_id: 订单 ID
            filled_amount: 成交数量
        """
        # 查找对应的网格和档位
        for grid in self._grids.values():
            for level_idx, level in grid.levels.items():
                if level.order_id == order_id:
                    # 标记成交
                    grid.mark_level_filled(level_idx, Decimal(str(filled_amount)))

                    # 重置订单 ID，允许重新挂单
                    level.order_id = None

                    logger.info(
                        f"网格成交：{grid.id} {level.side} {filled_amount} @ {level.price} "
                        f"利润：{grid.profit:.2f}"
                    )
                    break

    def stop_grid(self, grid_id: str) -> bool:
        """停止网格交易"""
        grid = self._grids.get(grid_id)
        if not grid:
            return False

        grid.status = GridStatus.STOPPED
        logger.info(f"网格交易已停止：{grid_id}")
        return True

    def get_grid(self, grid_id: str) -> Optional[GridTrading]:
        """获取网格交易"""
        return self._grids.get(grid_id)

    def get_active_grids(self) -> List[GridTrading]:
        """获取所有运行中的网格"""
        return [g for g in self._grids.values() if g.status == GridStatus.RUNNING]

    def get_grid_stats(self, grid_id: str) -> Dict:
        """获取网格统计"""
        grid = self._grids.get(grid_id)
        if not grid:
            return {}

        return {
            "id": grid.id,
            "symbol": grid.symbol,
            "status": grid.status.value,
            "lower_price": float(grid.lower_price),
            "upper_price": float(grid.upper_price),
            "grid_num": grid.grid_num,
            "current_price": float(grid.current_price),
            "profit": float(grid.profit),
            "buy_count": grid.buy_count,
            "sell_count": grid.sell_count,
            "total_amount": float(grid.total_amount),
        }
