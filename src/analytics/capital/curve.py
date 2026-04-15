"""
资金曲线分析

提供资金变化图表数据和每日盈亏统计
"""
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from decimal import Decimal


class CapitalCurveAnalyzer:
    """
    资金曲线分析器

    功能:
    - 资金曲线数据
    - 每日盈亏统计
    - 累计盈亏曲线
    - 资金投入产出比
    """

    def __init__(self, initial_capital: float = 10000.0):
        """
        初始化分析器

        Args:
            initial_capital: 初始资金
        """
        self.initial_capital = initial_capital

    def analyze_capital_curve(
        self,
        daily_values: List[Dict],
    ) -> Dict:
        """
        分析资金曲线

        Args:
            daily_values: 每日资金数据，每项包含：
                - date: 日期
                - value: 资金总额

        Returns:
            分析结果字典
        """
        if not daily_values:
            return self._empty_result()

        # 提取数据
        dates = []
        values = []

        for item in daily_values:
            date = item.get('date')
            value = item.get('value', 0)

            if isinstance(date, str):
                date = datetime.fromisoformat(date)

            dates.append(date)
            values.append(value)

        # 计算累计收益率
        returns = []
        for v in values:
            ret = (v - self.initial_capital) / self.initial_capital * 100
            returns.append(ret)

        # 计算每日盈亏
        daily_pnl = []
        for i in range(len(values)):
            if i == 0:
                pnl = values[i] - self.initial_capital
            else:
                pnl = values[i] - values[i-1]
            daily_pnl.append(pnl)

        # 找出最高点和最低点
        max_value = max(values)
        min_value = min(values)
        max_date = dates[values.index(max_value)]
        min_date = dates[values.index(min_value)]

        # 当前资金
        current_value = values[-1] if values else 0
        total_return = (current_value - self.initial_capital) / self.initial_capital * 100

        return {
            "initial_capital": self.initial_capital,
            "current_value": current_value,
            "total_return": round(total_return, 2),
            "max_value": round(max_value, 2),
            "max_date": max_date.isoformat() if max_date else None,
            "min_value": round(min_value, 2),
            "min_date": min_date.isoformat() if min_date else None,
            "curve_data": [
                {
                    "date": d.isoformat() if isinstance(d, datetime) else str(d),
                    "value": round(v, 2),
                    "return": round(r, 2),
                }
                for d, v, r in zip(dates, values, returns)
            ],
            "daily_pnl": [
                {
                    "date": dates[i].isoformat() if isinstance(dates[i], datetime) else str(dates[i]),
                    "pnl": round(pnl, 2),
                }
                for i, pnl in enumerate(daily_pnl)
            ],
        }

    def analyze_daily_pnl(
        self,
        trades: List[Dict],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict:
        """
        分析每日盈亏

        Args:
            trades: 交易记录列表
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            每日盈亏统计
        """
        if not trades:
            return {"daily_pnl": {}, "summary": {}}

        # 按日期分组盈亏
        daily_pnl = {}

        for t in trades:
            exit_time = t.get('exit_time')
            pnl = t.get('pnl', 0)

            if not exit_time:
                continue

            if isinstance(exit_time, str):
                exit_time = datetime.fromisoformat(exit_time)

            # 日期过滤
            if start_date and exit_time < start_date:
                continue
            if end_date and exit_time > end_date:
                continue

            date_key = exit_time.strftime('%Y-%m-%d')

            if date_key not in daily_pnl:
                daily_pnl[date_key] = {
                    'pnl': 0,
                    'trades': 0,
                    'wins': 0,
                    'losses': 0,
                }

            daily_pnl[date_key]['pnl'] += pnl
            daily_pnl[date_key]['trades'] += 1

            if pnl > 0:
                daily_pnl[date_key]['wins'] += 1
            elif pnl < 0:
                daily_pnl[date_key]['losses'] += 1

        # 格式化输出
        result = {}
        for date, stats in sorted(daily_pnl.items()):
            result[date] = {
                'pnl': round(stats['pnl'], 2),
                'trades': stats['trades'],
                'wins': stats['wins'],
                'losses': stats['losses'],
            }

        # 汇总统计
        total_pnl = sum(stats['pnl'] for stats in daily_pnl.values())
        profitable_days = sum(1 for stats in daily_pnl.values() if stats['pnl'] > 0)
        losing_days = sum(1 for stats in daily_pnl.values() if stats['pnl'] < 0)
        total_days = len(daily_pnl)

        summary = {
            'total_pnl': round(total_pnl, 2),
            'profitable_days': profitable_days,
            'losing_days': losing_days,
            'total_days': total_days,
            'profit_day_ratio': round(profitable_days / total_days * 100, 2) if total_days > 0 else 0,
            'avg_daily_pnl': round(total_pnl / total_days, 2) if total_days > 0 else 0,
        }

        return {
            "daily_pnl": result,
            "summary": summary,
        }

    def _empty_result(self) -> Dict:
        """返回空结果"""
        return {
            "initial_capital": self.initial_capital,
            "current_value": 0,
            "total_return": 0,
            "max_value": 0,
            "max_date": None,
            "min_value": 0,
            "min_date": None,
            "curve_data": [],
            "daily_pnl": [],
        }
