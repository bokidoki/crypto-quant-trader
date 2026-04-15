"""
绩效指标计算

提供夏普比率、最大回撤、年化收益等指标计算
"""
from typing import List, Dict, Optional
from decimal import Decimal
import math


class PerformanceMetrics:
    """
    绩效指标计算器

    功能:
    - 总收益率
    - 年化收益率
    - 夏普比率
    - 最大回撤
    - 胜率
    - 盈亏比
    """

    def __init__(self, initial_capital: float = 10000.0):
        """
        初始化绩效计算器

        Args:
            initial_capital: 初始资金
        """
        self.initial_capital = initial_capital

    def calculate_total_return(self, current_value: float) -> float:
        """
        计算总收益率

        Args:
            current_value: 当前资金

        Returns:
            总收益率（百分比）
        """
        if self.initial_capital <= 0:
            return 0.0
        return (current_value - self.initial_capital) / self.initial_capital * 100

    def calculate_annualized_return(
        self,
        current_value: float,
        days: int
    ) -> float:
        """
        计算年化收益率

        Args:
            current_value: 当前资金
            days: 交易天数

        Returns:
            年化收益率（百分比）
        """
        if self.initial_capital <= 0 or days <= 0:
            return 0.0

        total_return = (current_value - self.initial_capital) / self.initial_capital
        years = days / 365.0

        if years <= 0:
            return total_return * 100

        # 年化收益率 = (1 + 总收益率) ^ (1/年数) - 1
        annualized = (1 + total_return) ** (1 / years) - 1
        return annualized * 100

    def calculate_sharpe_ratio(
        self,
        returns: List[float],
        risk_free_rate: float = 0.02
    ) -> float:
        """
        计算夏普比率

        Args:
            returns: 收益率序列（日收益率）
            risk_free_rate: 无风险利率（年化）

        Returns:
            夏普比率
        """
        if not returns or len(returns) < 2:
            return 0.0

        # 平均收益率
        avg_return = sum(returns) / len(returns)

        # 收益率标准差
        variance = sum((r - avg_return) ** 2 for r in returns) / (len(returns) - 1)
        std_dev = math.sqrt(variance) if variance > 0 else 0

        if std_dev == 0:
            return 0.0

        # 日化无风险利率
        daily_rf = risk_free_rate / 252

        # 夏普比率 = (平均收益率 - 无风险利率) / 标准差
        sharpe = (avg_return - daily_rf) / std_dev

        # 年化夏普比率
        return sharpe * math.sqrt(252)

    def calculate_max_drawdown(self, values: List[float]) -> float:
        """
        计算最大回撤

        Args:
            values: 资金曲线序列

        Returns:
            最大回撤（百分比）
        """
        if not values or len(values) < 2:
            return 0.0

        max_drawdown = 0.0
        peak = values[0]

        for value in values:
            if value > peak:
                peak = value

            drawdown = (peak - value) / peak if peak > 0 else 0
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        return max_drawdown * 100

    def calculate_win_rate(self, trades: List[Dict]) -> float:
        """
        计算胜率

        Args:
            trades: 交易记录列表，每项包含 {'pnl': float}

        Returns:
            胜率（百分比）
        """
        if not trades:
            return 0.0

        wins = sum(1 for t in trades if t.get('pnl', 0) > 0)
        return wins / len(trades) * 100

    def calculate_profit_loss_ratio(self, trades: List[Dict]) -> float:
        """
        计算盈亏比

        Args:
            trades: 交易记录列表，每项包含 {'pnl': float}

        Returns:
            盈亏比
        """
        if not trades:
            return 0.0

        wins = [t['pnl'] for t in trades if t['pnl'] > 0]
        losses = [abs(t['pnl']) for t in trades if t['pnl'] < 0]

        if not losses:
            return float('inf') if wins else 0.0

        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0

        if avg_loss == 0:
            return float('inf') if avg_win > 0 else 0.0

        return avg_win / avg_loss

    def calculate_all_metrics(
        self,
        current_value: float,
        days: int,
        daily_values: List[float],
        daily_returns: List[float],
        trades: List[Dict],
    ) -> Dict:
        """
        计算所有绩效指标

        Args:
            current_value: 当前资金
            days: 交易天数
            daily_values: 每日资金序列
            daily_returns: 每日收益率序列
            trades: 交易记录列表

        Returns:
            绩效指标字典
        """
        return {
            "initial_capital": self.initial_capital,
            "current_value": current_value,
            "total_return": self.calculate_total_return(current_value),
            "annualized_return": self.calculate_annualized_return(current_value, days),
            "sharpe_ratio": self.calculate_sharpe_ratio(daily_returns),
            "max_drawdown": self.calculate_max_drawdown(daily_values),
            "win_rate": self.calculate_win_rate(trades),
            "profit_loss_ratio": self.calculate_profit_loss_ratio(trades),
            "total_trades": len(trades),
            "win_trades": sum(1 for t in trades if t['pnl'] > 0),
            "loss_trades": sum(1 for t in trades if t['pnl'] < 0),
        }
