"""
策略对比分析

提供多策略收益对比、策略贡献度分析
"""
from typing import Dict, List, Optional
from datetime import datetime


class StrategyComparator:
    """
    策略对比分析器

    功能:
    - 多策略收益对比
    - 策略贡献度分析
    - 策略相关性分析
    - 策略排名
    """

    def __init__(self):
        """初始化分析器"""
        pass

    def compare_strategies(
        self,
        strategy_performance: Dict[str, Dict],
    ) -> Dict:
        """
        对比多个策略的表现

        Args:
            strategy_performance: 策略表现字典
                {
                    "strategy_name": {
                        "pnl": float,          # 盈亏
                        "return": float,       # 收益率
                        "sharpe": float,       # 夏普比率
                        "max_drawdown": float, # 最大回撤
                        "win_rate": float,     # 胜率
                        "trades": int,         # 交易次数
                    }
                }

        Returns:
            对比分析结果
        """
        if not strategy_performance:
            return {'ranking': [], 'summary': {}}

        # 策略排名（按收益率）
        ranking = []
        for name, perf in sorted(
            strategy_performance.items(),
            key=lambda x: x[1].get('return', 0),
            reverse=True
        ):
            ranking.append({
                'rank': len(ranking) + 1,
                'strategy': name,
                'return': round(perf.get('return', 0), 2),
                'pnl': round(perf.get('pnl', 0), 2),
                'sharpe': round(perf.get('sharpe', 0), 2),
                'max_drawdown': round(perf.get('max_drawdown', 0), 2),
                'win_rate': round(perf.get('win_rate', 0), 2),
                'trades': perf.get('trades', 0),
            })

        # 总结统计
        returns = [p.get('return', 0) for p in strategy_performance.values()]
        sharpes = [p.get('sharpe', 0) for p in strategy_performance.values()]
        drawdowns = [p.get('max_drawdown', 0) for p in strategy_performance.values()]

        summary = {
            'total_strategies': len(strategy_performance),
            'avg_return': round(sum(returns) / len(returns), 2) if returns else 0,
            'best_strategy': ranking[0]['strategy'] if ranking else None,
            'best_return': round(max(returns), 2) if returns else 0,
            'avg_sharpe': round(sum(sharpes) / len(sharpes), 2) if sharpes else 0,
            'min_drawdown': round(min(drawdowns), 2) if drawdowns else 0,
        }

        return {
            'ranking': ranking,
            'summary': summary,
        }

    def analyze_contribution(
        self,
        strategy_pnl: Dict[str, float],
    ) -> Dict:
        """
        分析策略贡献度

        Args:
            strategy_pnl: 策略盈亏字典 {strategy_name: pnl}

        Returns:
            贡献度分析结果
        """
        if not strategy_pnl:
            return {'contribution': [], 'summary': {}}

        # 总盈亏
        total_pnl = sum(strategy_pnl.values())
        total_positive = sum(pnl for pnl in strategy_pnl.values() if pnl > 0)
        total_negative = sum(pnl for pnl in strategy_pnl.values() if pnl < 0)

        # 计算贡献度
        contribution = []
        for name, pnl in sorted(strategy_pnl.items(), key=lambda x: x[1], reverse=True):
            if total_pnl != 0:
                contribution_pct = (pnl / abs(total_pnl) * 100) if total_pnl > 0 else -(pnl / abs(total_pnl) * 100)
            else:
                contribution_pct = 0

            contribution.append({
                'strategy': name,
                'pnl': round(pnl, 2),
                'contribution_pct': round(contribution_pct, 2),
                'is_positive': pnl > 0,
            })

        # 总结
        profitable_strategies = [c for c in contribution if c['is_positive']]
        losing_strategies = [c for c in contribution if not c['is_positive']]

        summary = {
            'total_pnl': round(total_pnl, 2),
            'profitable_strategies': len(profitable_strategies),
            'losing_strategies': len(losing_strategies),
            'total_positive_contribution': round(sum(c['pnl'] for c in profitable_strategies), 2),
            'total_negative_contribution': round(abs(sum(c['pnl'] for c in losing_strategies)), 2),
        }

        return {
            'contribution': contribution,
            'summary': summary,
        }

    def analyze_correlation(
        self,
        strategy_returns: Dict[str, List[float]],
    ) -> Dict:
        """
        分析策略相关性

        Args:
            strategy_returns: 策略收益率序列
                {
                    "strategy_a": [0.01, -0.02, 0.03, ...],
                    "strategy_b": [0.02, 0.01, -0.01, ...],
                }

        Returns:
            相关性矩阵
        """
        if not strategy_returns or len(strategy_returns) < 2:
            return {'correlation_matrix': {}}

        strategies = list(strategy_returns.keys())
        n = len(strategies)

        # 计算相关系数矩阵
        correlation_matrix = {}

        for i, s1 in enumerate(strategies):
            correlation_matrix[s1] = {}
            returns1 = strategy_returns[s1]

            for j, s2 in enumerate(strategies):
                if i == j:
                    correlation_matrix[s1][s2] = 1.0
                else:
                    returns2 = strategy_returns[s2]
                    corr = self._calculate_correlation(returns1, returns2)
                    correlation_matrix[s1][s2] = round(corr, 4)

        return {
            'strategies': strategies,
            'correlation_matrix': correlation_matrix,
        }

    def _calculate_correlation(self, x: List[float], y: List[float]) -> float:
        """计算皮尔逊相关系数"""
        n = min(len(x), len(y))
        if n < 2:
            return 0.0

        x = x[:n]
        y = y[:n]

        mean_x = sum(x) / n
        mean_y = sum(y) / n

        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))

        sum_sq_x = sum((xi - mean_x) ** 2 for xi in x)
        sum_sq_y = sum((yi - mean_y) ** 2 for yi in y)

        denominator = (sum_sq_x * sum_sq_y) ** 0.5

        if denominator == 0:
            return 0.0

        return numerator / denominator
