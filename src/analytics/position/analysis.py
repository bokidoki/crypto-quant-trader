"""
持仓分析

提供币种持仓占比、未实现盈亏等分析
"""
from typing import Dict, List, Optional
from decimal import Decimal


class PositionAnalyzer:
    """
    持仓分析器

    功能:
    - 币种持仓占比
    - 未实现盈亏
    - 持仓集中度
    - 持仓分布
    """

    def __init__(self):
        """初始化分析器"""
        pass

    def analyze_positions(
        self,
        positions: List[Dict],
        current_prices: Dict[str, float],
    ) -> Dict:
        """
        分析持仓

        Args:
            positions: 持仓列表，每项包含：
                - symbol: 交易对
                - quantity: 数量
                - entry_price: 入场价
            current_prices: 当前价格字典 {symbol: price}

        Returns:
            持仓分析结果
        """
        if not positions:
            return self._empty_result()

        total_value = 0
        total_cost = 0
        position_details = []

        for pos in positions:
            symbol = pos.get('symbol', '')
            quantity = Decimal(str(pos.get('quantity', 0)))
            entry_price = Decimal(str(pos.get('entry_price', 0)))

            # 获取当前价格
            current_price = Decimal(str(current_prices.get(symbol, 0)))

            # 计算价值
            position_value = float(quantity * current_price)
            cost_basis = float(quantity * entry_price)

            # 计算盈亏
            unrealized_pnl = float(quantity * (current_price - entry_price))
            unrealized_pnl_percent = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

            total_value += position_value
            total_cost += cost_basis

            position_details.append({
                'symbol': symbol,
                'quantity': float(quantity),
                'entry_price': float(entry_price),
                'current_price': float(current_price),
                'position_value': round(position_value, 2),
                'unrealized_pnl': round(unrealized_pnl, 2),
                'unrealized_pnl_percent': round(unrealized_pnl_percent, 2),
            })

        # 计算持仓占比
        for pos in position_details:
            pos['weight'] = round(pos['position_value'] / total_value * 100, 2) if total_value > 0 else 0

        # 总未实现盈亏
        total_unrealized_pnl = total_value - total_cost
        total_unrealized_pnl_percent = ((total_value - total_cost) / total_cost * 100) if total_cost > 0 else 0

        # 持仓集中度（最大持仓占比）
        if position_details:
            max_weight = max(pos['weight'] for pos in position_details)
        else:
            max_weight = 0

        return {
            'total_value': round(total_value, 2),
            'total_cost': round(total_cost, 2),
            'total_unrealized_pnl': round(total_unrealized_pnl, 2),
            'total_unrealized_pnl_percent': round(total_unrealized_pnl_percent, 2),
            'position_count': len(position_details),
            'positions': position_details,
            'max_position_weight': round(max_weight, 2),
        }

    def analyze_position_distribution(
        self,
        positions: List[Dict],
        current_prices: Dict[str, float],
    ) -> Dict:
        """
        分析持仓分布

        Args:
            positions: 持仓列表
            current_prices: 当前价格字典

        Returns:
            持仓分布分析
        """
        if not positions:
            return {'distribution': [], 'summary': {}}

        # 按币种分类
        by_symbol = {}
        for pos in positions:
            symbol = pos.get('symbol', '')
            base_currency = symbol.split('/')[0] if '/' in symbol else symbol

            if base_currency not in by_symbol:
                by_symbol[base_currency] = {
                    'quantity': 0,
                    'value': 0,
                    'positions': [],
                }

            quantity = Decimal(str(pos.get('quantity', 0)))
            current_price = Decimal(str(current_prices.get(symbol, 0)))
            value = float(quantity * current_price)

            by_symbol[base_currency]['quantity'] += float(quantity)
            by_symbol[base_currency]['value'] += value
            by_symbol[base_currency]['positions'].append(pos)

        # 计算占比
        total_value = sum(data['value'] for data in by_symbol.values())
        distribution = []

        for currency, data in sorted(by_symbol.items(), key=lambda x: x[1]['value'], reverse=True):
            distribution.append({
                'currency': currency,
                'value': round(data['value'], 2),
                'weight': round(data['value'] / total_value * 100, 2) if total_value > 0 else 0,
                'position_count': len(data['positions']),
            })

        # 总结
        summary = {
            'total_currencies': len(by_symbol),
            'total_value': round(total_value, 2),
            'top_3_weight': sum(d['weight'] for d in distribution[:3]) if len(distribution) >= 3 else 100,
        }

        return {
            'distribution': distribution,
            'summary': summary,
        }

    def _empty_result(self) -> Dict:
        """返回空结果"""
        return {
            'total_value': 0,
            'total_cost': 0,
            'total_unrealized_pnl': 0,
            'total_unrealized_pnl_percent': 0,
            'position_count': 0,
            'positions': [],
            'max_position_weight': 0,
        }
