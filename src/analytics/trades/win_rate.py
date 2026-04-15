"""
交易记录分析

提供胜率、平均持仓时间等分析
"""
from typing import List, Dict, Optional
from datetime import datetime
from decimal import Decimal


class TradeAnalyzer:
    """
    交易记录分析器

    功能:
    - 胜率分析
    - 盈亏比分析
    - 平均持仓时间
    - 连续盈亏分析
    - 交易频率统计
    """

    def __init__(self):
        """初始化分析器"""
        pass

    def analyze_trades(self, trades: List[Dict]) -> Dict:
        """
        分析交易记录

        Args:
            trades: 交易记录列表，每项包含：
                - pnl: 盈亏金额
                - entry_time: 入场时间
                - exit_time: 出场时间
                - side: 方向 (buy/sell)
                - symbol: 交易对

        Returns:
            分析结果字典
        """
        if not trades:
            return self._empty_result()

        # 分类交易
        winning_trades = [t for t in trades if t.get('pnl', 0) > 0]
        losing_trades = [t for t in trades if t.get('pnl', 0) <= 0]

        # 计算盈亏
        total_pnl = sum(t.get('pnl', 0) for t in trades)
        gross_profit = sum(t.get('pnl', 0) for t in winning_trades)
        gross_loss = abs(sum(t.get('pnl', 0) for t in losing_trades))

        # 平均盈亏
        avg_win = gross_profit / len(winning_trades) if winning_trades else 0
        avg_loss = gross_loss / len(losing_trades) if losing_trades else 0

        # 盈亏比
        profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else float('inf')

        # 胜率
        win_rate = len(winning_trades) / len(trades) * 100 if trades else 0

        # 平均持仓时间
        holding_times = []
        for t in trades:
            entry = t.get('entry_time')
            exit = t.get('exit_time')
            if entry and exit:
                if isinstance(entry, str):
                    entry = datetime.fromisoformat(entry)
                if isinstance(exit, str):
                    exit = datetime.fromisoformat(exit)
                duration = (exit - entry).total_seconds() / 3600  # 小时
                holding_times.append(duration)

        avg_holding_time = sum(holding_times) / len(holding_times) if holding_times else 0

        # 连续盈亏分析
        max_consecutive_wins, max_consecutive_losses = self._analyze_consecutive(trades)

        # 按月统计
        monthly_stats = self._monthly_statistics(trades)

        return {
            "total_trades": len(trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_loss_ratio": round(profit_loss_ratio, 2) if profit_loss_ratio != float('inf') else "∞",
            "avg_holding_time_hours": round(avg_holding_time, 2),
            "max_consecutive_wins": max_consecutive_wins,
            "max_consecutive_losses": max_consecutive_losses,
            "monthly_stats": monthly_stats,
        }

    def _analyze_consecutive(self, trades: List[Dict]) -> tuple:
        """
        分析连续盈亏

        Args:
            trades: 交易记录列表

        Returns:
            (最大连续盈利次数，最大连续亏损次数)
        """
        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0

        for t in trades:
            pnl = t.get('pnl', 0)

            if pnl > 0:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)

        return max_wins, max_losses

    def _monthly_statistics(self, trades: List[Dict]) -> Dict:
        """
        按月统计交易

        Args:
            trades: 交易记录列表

        Returns:
            月度统计字典
        """
        monthly = {}

        for t in trades:
            exit_time = t.get('exit_time')
            if not exit_time:
                continue

            if isinstance(exit_time, str):
                exit_time = datetime.fromisoformat(exit_time)

            month_key = exit_time.strftime('%Y-%m')

            if month_key not in monthly:
                monthly[month_key] = {
                    'trades': 0,
                    'pnl': 0,
                    'wins': 0,
                    'losses': 0,
                }

            monthly[month_key]['trades'] += 1
            monthly[month_key]['pnl'] += t.get('pnl', 0)

            if t.get('pnl', 0) > 0:
                monthly[month_key]['wins'] += 1
            else:
                monthly[month_key]['losses'] += 1

        # 格式化输出
        result = {}
        for month, stats in sorted(monthly.items()):
            result[month] = {
                'trades': stats['trades'],
                'pnl': round(stats['pnl'], 2),
                'win_rate': round(stats['wins'] / stats['trades'] * 100, 2) if stats['trades'] > 0 else 0,
            }

        return result

    def _empty_result(self) -> Dict:
        """返回空结果"""
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0,
            "total_pnl": 0,
            "gross_profit": 0,
            "gross_loss": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "profit_loss_ratio": 0,
            "avg_holding_time_hours": 0,
            "max_consecutive_wins": 0,
            "max_consecutive_losses": 0,
            "monthly_stats": {},
        }
