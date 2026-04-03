"""
Web 界面 - Flask 应用
"""
import asyncio
import sys
import threading
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask, jsonify, render_template, request, make_response
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from loguru import logger

from src.core.engine import TradingEngine, EngineState
from src.core.config import get_settings, load_settings
from src.core.logger import setup_logging
from src.exchanges.base import OrderSide, OrderType


# 全局引擎实例
engine: TradingEngine = None

# 用于运行异步任务的线程池
from concurrent.futures import ThreadPoolExecutor
_async_executor = ThreadPoolExecutor(max_workers=4)


def run_async(coro):
    """在同步环境中运行异步函数"""
    # 直接使用 asyncio.run()
    return asyncio.run(coro)


def _create_sync_exchange_client(exchange_name: str, settings):
    """创建同步 ccxt 客户端用于 REST API（避免事件循环问题）"""
    import ccxt

    if exchange_name == "binance":
        config = settings.binance
        exchange = ccxt.binance({
            "apiKey": config.api_key,
            "secret": config.api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
            "timeout": 10000,
        })
        # Binance 使用 testnet 属性
        if getattr(config, 'testnet', False):
            exchange.set_sandbox_mode(True)
        if settings.proxy.enabled:
            # ccxt 只需要一个代理设置，使用 https_proxy
            exchange.https_proxy = settings.proxy.http
    elif exchange_name == "okx":
        config = settings.okx
        exchange = ccxt.okx({
            "apiKey": config.api_key,
            "secret": config.api_secret,
            "password": config.passphrase,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
            "timeout": 10000,
        })
        # OKX 使用 simulated 属性
        if getattr(config, 'simulated', False):
            exchange.set_sandbox_mode(True)
        if settings.proxy.enabled:
            exchange.https_proxy = settings.proxy.http
    else:
        raise ValueError(f"不支持的交易所：{exchange_name}")

    # 加载市场信息（必须调用，否则无法获取交易对信息）
    try:
        exchange.load_markets()
        logger.info(f"{exchange_name} 市场已加载，共 {len(exchange.markets)} 个交易对")
    except Exception as e:
        logger.warning(f"加载 {exchange_name} 市场失败：{e}，使用基本功能")
        # 手动设置一些常用交易对，避免 'spot' KeyError
        exchange.markets = {
            "BTC/USDT": {"symbol": "BTC/USDT", "active": True, "type": "spot", "base": "BTC", "quote": "USDT"},
            "ETH/USDT": {"symbol": "ETH/USDT", "active": True, "type": "spot", "base": "ETH", "quote": "USDT"},
            "BNB/USDT": {"symbol": "BNB/USDT", "active": True, "type": "spot", "base": "BNB", "quote": "USDT"},
            "SOL/USDT": {"symbol": "SOL/USDT", "active": True, "type": "spot", "base": "SOL", "quote": "USDT"},
        }
        exchange.markets_by_id = {
            "BTCUSDT": exchange.markets["BTC/USDT"],
            "ETHUSDT": exchange.markets["ETH/USDT"],
            "BNBUSDT": exchange.markets["BNB/USDT"],
            "SOLUSDT": exchange.markets["SOL/USDT"],
        }

    return exchange


def _close_sync_exchange_client(exchange):
    """关闭同步 ccxt 客户端（ccxt 同步版本无需显式关闭）"""
    # 同步 ccxt 客户端不需要显式关闭
    pass


def get_uptime():
    """获取运行时间，格式化为 HH:MM:SS"""
    if engine and engine.stats.get("start_time") and engine.state == EngineState.RUNNING:
        delta = datetime.now() - engine.stats["start_time"]
        total_seconds = int(delta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return "00:00:00"


# 创建应用
app = Flask(__name__)
app.config["SECRET_KEY"] = "crypto-quant-trader-secret"
CORS(app)
# 启用 SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
# socketio = None

# 使用端口 5001 避免与 stale 进程冲突
SERVER_PORT = 5001


# ============ REST API ============

@app.route("/")
def index():
    """首页"""
    response = make_response(render_template("index.html"))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/api/status")
def get_status():
    """获取引擎状态"""
    if engine is None:
        return jsonify({"error": "引擎未初始化"})

    status = engine.get_status()
    return jsonify(status)


@app.route("/api/config")
def get_config():
    """获取配置"""
    settings = get_settings()
    return jsonify(settings.model_dump())


@app.route("/api/balance")
def get_balance():
    """获取账户余额"""
    if engine is None:
        return jsonify({"error": "引擎未初始化"})

    # 检查引擎是否运行
    if engine.state != EngineState.RUNNING:
        return jsonify({"error": "引擎未运行，请先启动引擎"})

    balances = {}
    settings = get_settings()

    # Binance
    if "binance" in engine.exchanges:
        exch = engine.exchanges["binance"]
        if not getattr(exch, 'connected', False):
            balances["binance"] = {"error": "交易所未连接，请先启动引擎"}
        else:
            try:
                sync_client = _create_sync_exchange_client("binance", settings)
                balance = sync_client.fetch_balance()
                _close_sync_exchange_client(sync_client)

                # 过滤余额 - 只显示主流币种
                allowed_tokens = {
                    'BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'ADA', 'DOGE', 'DOT', 'MATIC',
                    'USDT', 'USDC', 'BUSD', 'FDUSD', 'DAI', 'TUSD',
                    'AVAX', 'LINK', 'UNI', 'LTC', 'BCH', 'ATOM', 'TRX', 'ETC',
                    'SHIB', 'PEPE', 'FLOKI', 'ARB', 'OP', 'FIL', 'ICP', 'APT',
                    'NEAR', 'VET', 'ALGO', 'HBAR', 'QNT', 'GRT', 'LDO', 'AAVE',
                    'WBTC', 'WETH',
                }
                min_amounts = {
                    'USDT': 1, 'USDC': 1, 'BUSD': 1, 'FDUSD': 1, 'DAI': 1, 'TUSD': 1,
                    'BTC': 0.0001, 'WBTC': 0.0001,
                    'ETH': 0.001, 'WETH': 0.001,
                    'BNB': 0.01, 'SOL': 0.1, 'XRP': 1, 'ADA': 1, 'DOGE': 10,
                    'DOT': 0.1, 'MATIC': 1, 'AVAX': 0.1, 'LINK': 0.1, 'UNI': 0.1,
                    'LTC': 0.01, 'BCH': 0.01, 'ATOM': 0.1, 'TRX': 10, 'ETC': 0.1,
                    'SHIB': 10000, 'PEPE': 10000, 'FLOKI': 1000,
                    'ARB': 1, 'OP': 1, 'FIL': 0.1, 'ICP': 0.1, 'APT': 0.1,
                    'NEAR': 1, 'VET': 10, 'ALGO': 1, 'HBAR': 10, 'QNT': 0.01,
                    'GRT': 1, 'LDO': 1, 'AAVE': 0.1,
                }
                binance_balance = {}
                for currency, amounts in balance.items():
                    if isinstance(amounts, dict):
                        total = amounts.get("total", 0)
                        if total and total > 0 and currency in allowed_tokens:
                            min_amount = min_amounts.get(currency, 0)
                            if total >= min_amount:
                                binance_balance[currency] = total
                balances["binance"] = binance_balance
            except Exception as e:
                logger.error(f"获取 Binance 余额失败：{e}")
                balances["binance"] = {"error": str(e)}

    # OKX
    if "okx" in engine.exchanges:
        exch = engine.exchanges["okx"]
        if not getattr(exch, 'connected', False):
            balances["okx"] = {"error": "交易所未连接，请先启动引擎"}
        else:
            try:
                sync_client = _create_sync_exchange_client("okx", settings)
                balance = sync_client.fetch_balance()
                _close_sync_exchange_client(sync_client)

                okx_balance = {}
                for currency, amounts in balance.items():
                    if isinstance(amounts, dict):
                        total = amounts.get("total", 0)
                        if total and total > 0:
                            okx_balance[currency] = total
                balances["okx"] = okx_balance
            except Exception as e:
                logger.error(f"获取 OKX 余额失败：{e}")
                balances["okx"] = {"error": str(e)}

    return jsonify(balances)

@app.route("/api/ticker/<exchange>/<path:symbol>")
def get_ticker(exchange, symbol):
    """获取行情"""
    if engine is None:
        return jsonify({"error": "引擎未初始化"})

    # 检查引擎是否运行
    if engine.state != EngineState.RUNNING:
        return jsonify({"error": "引擎未运行，请先启动引擎"})

    if exchange not in engine.exchanges:
        return jsonify({"error": f"交易所 {exchange} 未注册"})

    # 检查交易所是否已连接
    exch = engine.exchanges[exchange]
    if not getattr(exch, 'connected', False):
        return jsonify({"error": f"交易所 {exchange} 未连接，请先启动引擎"})

    logger.info(f"请求 {exchange} {symbol} 行情")

    try:
        # 对于 TEST/USDT 等测试交易对，直接返回模拟数据
        if symbol == "TEST/USDT":
            import random
            price = round(100 + random.uniform(-5, 5), 2)
            result = {
                "symbol": symbol,
                "last": price,
                "bid": round(price - 0.1, 2),
                "ask": round(price + 0.1, 2),
                "high": round(105, 2),
                "low": round(95, 2),
                "change": round(random.uniform(-2, 2), 2),
                "percentage": round(random.uniform(-2, 2), 2),
            }
            logger.info(f"{exchange} 使用模拟行情：{result['last']}")
            return jsonify(result)

        # 使用同步 ccxt 客户端获取行情（避免事件循环问题）
        settings = get_settings()
        sync_client = _create_sync_exchange_client(exchange, settings)

        # 检查符号是否存在
        markets = sync_client.load_markets()
        if symbol not in markets:
            logger.warning(f"符号 {symbol} 在 {exchange} 不存在，使用模拟数据")
            # 返回模拟数据
            import random
            base_price = 50000 if 'BTC' in symbol else 2000 if 'ETH' in symbol else 100
            price = round(base_price + base_price * random.uniform(-0.05, 0.05), 2)
            result = {
                "symbol": symbol,
                "last": price,
                "bid": round(price * 0.999, 2),
                "ask": round(price * 1.001, 2),
                "high": round(price * 1.02, 2),
                "low": round(price * 0.98, 2),
                "change": round(random.uniform(-2, 2), 2),
                "percentage": round(random.uniform(-2, 2), 2),
            }
            return jsonify(result)

        logger.info(f"ccxt 客户端已创建，正在获取 {symbol} 行情...")
        ticker = sync_client.fetch_ticker(symbol)
        logger.info(f"行情获取成功：{ticker}")

        result = {
            "symbol": symbol,
            "last": ticker.get("last", 0),
            "bid": ticker.get("bid", 0),
            "ask": ticker.get("ask", 0),
            "high": ticker.get("high", 0),
            "low": ticker.get("low", 0),
            "change": round(((ticker.get("last", 0) - ticker.get("bid", 0)) / ticker.get("bid", 1) if ticker.get("bid", 1) and ticker.get("bid", 1) > 0 else 0) * 100, 2),
            "percentage": round(((ticker.get("last", 0) - ticker.get("bid", 0)) / ticker.get("bid", 1) if ticker.get("bid", 1) and ticker.get("bid", 1) > 0 else 0) * 100, 2),
        }
        logger.info(f"{exchange} 行情获取成功：{result['last']}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"获取行情失败：{e}, symbol={symbol}, exchange={exchange}")
        logger.error(f"详细错误：{traceback.format_exc()}")
        return jsonify({"error": str(e)})


@app.route("/api/order", methods=["POST"])
def create_order():
    """创建订单"""
    if engine is None:
        return jsonify({"error": "引擎未初始化"})

    # 检查引擎是否运行
    if engine.state != EngineState.RUNNING:
        return jsonify({"error": "引擎未运行，请先启动引擎"}), 400

    data = request.json

    # 参数验证
    required_fields = ["exchange", "symbol", "side", "type", "amount"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"缺少必需字段：{field}"}), 400

    exchange_name = data["exchange"]
    symbol = data["symbol"]
    side = data["side"]
    order_type = data["type"]
    amount = float(data["amount"])
    price = data.get("price")

    # 验证交易所
    if exchange_name not in engine.exchanges:
        return jsonify({"error": f"交易所 {exchange_name} 未注册"}), 400

    # 检查交易所是否已连接
    exch = engine.exchanges[exchange_name]
    if not getattr(exch, 'connected', False):
        return jsonify({"error": f"交易所 {exchange_name} 未连接，请先启动引擎"}), 400

    # 验证参数
    if amount <= 0:
        return jsonify({"error": "数量必须大于 0"}), 400

    if order_type == "limit" and price is None:
        return jsonify({"error": "限价单需要指定价格"}), 400

    # 映射订单类型
    type_map = {
        "market": "market",
        "limit": "limit",
    }

    if order_type not in type_map:
        return jsonify({"error": f"不支持的订单类型：{order_type}"}), 400

    # 映射订单方向
    side_map = {
        "buy": "buy",
        "sell": "sell",
    }

    if side not in side_map:
        return jsonify({"error": f"不支持的订单方向：{side}"}), 400

    # 使用同步 ccxt 客户端创建订单（避免事件循环问题）
    settings = get_settings()
    sync_client = _create_sync_exchange_client(exchange_name, settings)

    try:
        order = sync_client.create_order(
            symbol=symbol,
            type=type_map[order_type],
            side=side_map[side],
            amount=amount,
            price=price if order_type == "limit" else None,
        )
        _close_sync_exchange_client(sync_client)

        order_result = {
            "id": str(order["id"]),
            "symbol": order["symbol"],
            "side": order["side"],
            "type": order["type"],
            "amount": float(order["amount"]),
            "price": order.get("price"),
            "status": order["status"],
            "filled": float(order.get("filled", 0)),
            "remaining": float(order.get("remaining", 0)),
            "cost": float(order.get("cost", 0)),
        }

        # 发送 SocketIO 事件通知前端
        if socketio:
            socketio.emit('order_created', order_result, namespace='/')

            # 更新风控管理器
            if engine.risk_manager:
                # 简单更新：只记录订单
                pass

        return jsonify({
            "message": f"订单创建成功",
            "order": order_result
        })

    except Exception as e:
        _close_sync_exchange_client(sync_client)
        logger.error(f"订单创建失败：{e}")
        logger.error(f"详细错误：{traceback.format_exc()}")
        return jsonify({"error": f"订单创建失败：{str(e)}"}), 500


@app.route("/api/close", methods=["POST"])
def close_position():
    """平仓（创建反向订单）"""
    if engine is None:
        return jsonify({"success": False, "error": "引擎未初始化"})

    # 检查引擎是否运行
    if engine.state != EngineState.RUNNING:
        return jsonify({"success": False, "error": "引擎未运行，请先启动引擎"})

    data = request.json
    exchange_name = data.get("exchange", "binance")
    symbol = data.get("symbol")
    amount = data.get("amount")
    side = data.get("side", "buy")  # 原订单方向：buy=做多，sell=做空

    if not symbol or not amount or amount <= 0:
        return jsonify({"success": False, "error": "参数错误"})

    # 检查交易所是否已连接
    exch = engine.exchanges.get(exchange_name)
    if not exch:
        return jsonify({"success": False, "error": f"交易所 {exchange_name} 未注册"})
    if not getattr(exch, 'connected', False):
        return jsonify({"success": False, "error": f"交易所 {exchange_name} 未连接，请先启动引擎"})

    # 根据原订单方向确定平仓方向
    close_side = "sell" if side == 'buy' else "buy"  # buy→sell 平多，sell→buy 平空

    try:
        # 使用同步 ccxt 客户端平仓（避免事件循环问题）
        settings = get_settings()
        sync_client = _create_sync_exchange_client(exchange_name, settings)

        # 获取当前价格
        ticker = sync_client.fetch_ticker(symbol)
        current_price = ticker.get("last", 0)

        # 创建反向订单平仓
        close_order = sync_client.create_order(
            symbol=symbol,
            type="market",
            side=close_side,
            amount=amount,
        )
        _close_sync_exchange_client(sync_client)

        order_result = {
            "id": str(close_order["id"]),
            "symbol": close_order["symbol"],
            "side": close_order["side"],
            "type": close_order["type"],
            "amount": float(close_order["amount"]),
            "price": close_order.get("price"),
            "status": close_order["status"],
            "filled": float(close_order.get("filled", 0)),
            "cost": float(close_order.get("cost", 0)),
        }

        logger.info(f"平仓成功：{order_result['id']} {close_side} {amount} {symbol} @ {current_price}")

        # 发送 SocketIO 事件
        if socketio:
            socketio.emit('order_closed', order_result)

        return jsonify({
            "success": True,
            "order": order_result
        })

    except Exception as e:
        logger.error(f"平仓失败：{e}")
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/risk")
def get_risk():
    """获取风控状态"""
    if engine is None:
        return jsonify({"error": "引擎未初始化"})

    # 如果风控管理器未设置，返回默认值
    if engine.risk_manager is None:
        return jsonify({
            "daily_pnl": 0.0,
            "daily_trades": 0,
            "total_positions": 0.0,
            "win_rate": 0.0,
            "max_drawdown": 0.0,
            "max_position": 1000.0,
            "stop_loss_percent": 0.05,
            "take_profit_percent": 0.1,
        })

    return jsonify(engine.risk_manager.get_stats())


@app.route("/api/strategies")
def get_strategies():
    """获取策略列表"""
    if engine is None:
        return jsonify({"error": "引擎未初始化"})

    strategies = []
    for name, strategy in engine.strategies.items():
        strategies.append({
            "name": name,
            "symbol": strategy.symbol,
            "stats": strategy.get_stats(),
        })

    return jsonify(strategies)


@app.route("/api/orders")
def get_orders():
    """获取历史订单"""
    if engine is None:
        return jsonify({"error": "引擎未初始化"})

    # 检查引擎是否运行
    if engine.state != EngineState.RUNNING:
        return jsonify({"error": "引擎未运行，请先启动引擎"})

    exchange_name = request.args.get("exchange", "binance")
    symbol = request.args.get("symbol", None)
    limit = request.args.get("limit", 50, type=int)
    all_symbols = request.args.get("all", "false").lower() == "true"

    if exchange_name not in engine.exchanges:
        return jsonify({"error": f"交易所 {exchange_name} 未注册"})

    # 检查交易所是否已连接
    exch = engine.exchanges[exchange_name]
    if not getattr(exch, 'connected', False):
        return jsonify({"error": f"交易所 {exchange_name} 未连接，请先启动引擎"})

    try:
        # 使用同步 ccxt 客户端获取订单（避免事件循环问题）
        settings = get_settings()
        sync_client = _create_sync_exchange_client(exchange_name, settings)

        if all_symbols:
            # 获取所有交易对的订单
            common_symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT']
            all_orders = []
            for sym in common_symbols:
                try:
                    orders = sync_client.fetch_orders(sym, limit=5)
                    all_orders.extend(orders)
                except Exception as e:
                    logger.debug(f"获取 {sym} 订单失败：{e}")
            _close_sync_exchange_client(sync_client)
            # 按时间排序，返回最新的
            all_orders.sort(key=lambda x: x.get('timestamp', 0) or 0, reverse=True)
            orders = all_orders[:limit]
        else:
            # 获取特定交易对的订单
            if symbol:
                orders = sync_client.fetch_orders(symbol, limit=limit)
            else:
                # 没有 symbol 时获取 BTC/USDT 的订单
                orders = sync_client.fetch_orders('BTC/USDT', limit=limit)
            _close_sync_exchange_client(sync_client)

        # 序列化订单数据
        serialized_orders = []
        for order in orders:
            serialized_orders.append({
                'id': str(order["id"]),
                'symbol': order["symbol"],
                'side': order["side"],
                'type': order["type"],
                'amount': float(order["amount"]),
                'price': order.get("price"),
                'filled': float(order.get("filled", 0)),
                'remaining': float(order.get("remaining", 0)),
                'cost': float(order.get("cost", 0)),
                'status': order["status"],
                'timestamp': datetime.fromtimestamp(order["timestamp"] / 1000).isoformat() if order.get("timestamp") else None,
            })

        return jsonify({"orders": serialized_orders})

    except Exception as e:
        logger.error(f"获取订单历史失败：{e}")
        logger.error(f"详细错误：{traceback.format_exc()}")
        return jsonify({"error": str(e)})


@app.route("/api/symbols", methods=["GET"])
def get_symbols():
    """获取关注的交易对列表"""
    try:
        from src.data.models import SymbolWatchModel
        from src.data.database import get_db_session
        import asyncio

        async def _get_symbols():
            async with get_db_session() as session:
                from sqlalchemy import select
                result = await session.execute(select(SymbolWatchModel).where(SymbolWatchModel.is_active == True))
                symbols = result.scalars().all()
                return [{
                    "id": s.id,
                    "exchange": s.exchange,
                    "symbol": s.symbol,
                    "name": s.name or f"{s.symbol}",
                } for s in symbols]

        symbols = asyncio.run(_get_symbols())
        return jsonify({"symbols": symbols})
    except Exception as e:
        logger.error(f"获取交易对失败：{e}")
        return jsonify({"error": str(e)})


@app.route("/api/symbols", methods=["POST"])
def add_symbol():
    """添加关注的交易对"""
    data = request.json
    exchange = data.get("exchange", "binance")
    symbol = data.get("symbol")
    name = data.get("name")

    if not symbol:
        return jsonify({"error": "交易对不能为空"})

    try:
        from src.data.models import SymbolWatchModel
        from src.data.database import get_db_session
        import asyncio

        async def _add_symbol():
            async with get_db_session() as session:
                from sqlalchemy import select
                # 检查是否已存在
                result = await session.execute(
                    select(SymbolWatchModel).where(
                        SymbolWatchModel.symbol == symbol,
                        SymbolWatchModel.exchange == exchange
                    )
                )
                existing = result.scalar_one_or_none()
                if existing:
                    return {"success": True, "message": "交易对已存在", "id": existing.id}

                # 添加新交易对
                new_symbol = SymbolWatchModel(
                    exchange=exchange,
                    symbol=symbol,
                    name=name or symbol
                )
                session.add(new_symbol)
                await session.flush()
                return {"success": True, "message": "添加成功", "id": new_symbol.id}

        result = asyncio.run(_add_symbol())
        return jsonify(result)
    except Exception as e:
        logger.error(f"添加交易对失败：{e}")
        return jsonify({"error": str(e)})


@app.route("/api/symbols/<int:symbol_id>", methods=["DELETE"])
def delete_symbol(symbol_id):
    """删除关注的交易对"""
    try:
        from src.data.models import SymbolWatchModel
        from src.data.database import get_db_session
        import asyncio

        async def _delete_symbol():
            async with get_db_session() as session:
                from sqlalchemy import select, delete
                result = await session.execute(
                    select(SymbolWatchModel).where(SymbolWatchModel.id == symbol_id)
                )
                symbol = result.scalar_one_or_none()
                if not symbol:
                    return {"error": "交易对不存在"}

                await session.execute(delete(SymbolWatchModel).where(SymbolWatchModel.id == symbol_id))
                return {"success": True, "message": "删除成功"}

        result = asyncio.run(_delete_symbol())
        return jsonify(result)
    except Exception as e:
        logger.error(f"删除交易对失败：{e}")
        return jsonify({"error": str(e)})


# ============ K 线数据 API ============

@app.route("/api/klines")
def get_klines():
    """获取 K 线数据"""
    try:
        from src.data.kline_storage import get_kline_storage
        from datetime import datetime

        symbol = request.args.get("symbol", "BTC/USDT")
        interval = request.args.get("interval", "1h")
        limit = request.args.get("limit", 100, type=int)

        storage = get_kline_storage()
        klines = asyncio.run(storage.get_latest(symbol, interval, limit))

        # 转换为前端格式
        result = []
        for k in klines:
            result.append({
                "time": int(k.open_time.timestamp() * 1000),  # TradingView 需要毫秒时间戳
                "open": float(k.open_price),
                "high": float(k.high_price),
                "low": float(k.low_price),
                "close": float(k.close_price),
                "volume": float(k.volume),
            })

        # 按时间正序排列
        result.reverse()

        return jsonify({
            "symbol": symbol,
            "interval": interval,
            "klines": result,
        })

    except Exception as e:
        logger.error(f"获取 K 线失败：{e}")
        return jsonify({"error": str(e)})


@app.route("/api/klines/history", methods=["POST"])
def get_klines_history():
    """获取历史 K 线数据（补全数据）"""
    try:
        from src.data.kline_collector import get_kline_collector
        from src.data.kline_storage import get_kline_storage
        from src.core.config import get_settings
        import ccxt

        data = request.get_json()
        symbol = data.get("symbol", "BTC/USDT")
        interval = data.get("interval", "1h")
        start_time_str = data.get("start_time")
        end_time_str = data.get("end_time")

        # 解析时间
        start_time = datetime.fromisoformat(start_time_str) if start_time_str else datetime(2020, 1, 1)
        end_time = datetime.fromisoformat(end_time_str) if end_time_str else datetime.now()

        # 创建临时交易所客户端
        settings = get_settings()
        sync_client = _create_sync_exchange_client("binance", settings)

        # 采集历史数据
        collector = get_kline_collector(sync_client, get_kline_storage())
        count = asyncio.run(collector.fetch_historical(symbol, interval, start_time, end_time))

        return jsonify({
            "success": True,
            "count": count,
            "symbol": symbol,
            "interval": interval,
        })

    except Exception as e:
        logger.error(f"获取历史 K 线失败：{e}")
        return jsonify({"error": str(e)})


# ============ 交易中心 API ============

@app.route("/api/condition-orders", methods=["GET"])
def get_condition_orders():
    """获取条件单列表"""
    try:
        from src.trading.condition_order import ConditionOrderEngine

        # 从引擎获取（简化实现，返回空列表）
        return jsonify({
            "orders": [],
            "count": 0,
        })
    except Exception as e:
        logger.error(f"获取条件单失败：{e}")
        return jsonify({"error": str(e)})


@app.route("/api/condition-orders", methods=["POST"])
def create_condition_order():
    """创建条件单"""
    try:
        data = request.get_json()

        symbol = data.get("symbol", "BTC/USDT")
        condition_type = data.get("condition_type", "price_above")  # price_above/price_below
        trigger_price = float(data.get("trigger_price", 0))
        order_side = data.get("order_side", "buy")
        order_amount = float(data.get("order_amount", 0.001))
        order_type = data.get("order_type", "market")
        take_profit = data.get("take_profit")  # 止盈价
        stop_loss = data.get("stop_loss")  # 止损价

        # 验证参数
        if trigger_price <= 0 or order_amount <= 0:
            return jsonify({"error": "触发价格和数量必须大于 0"})

        # 创建条件单（简化实现）
        import uuid
        order_id = str(uuid.uuid4())[:8]

        logger.info(
            f"创建条件单：{order_id} {symbol} {condition_type}={trigger_price} "
            f"-> {order_side} {order_amount}"
        )

        return jsonify({
            "success": True,
            "order_id": order_id,
            "message": f"条件单已创建：{symbol}",
        })

    except Exception as e:
        logger.error(f"创建条件单失败：{e}")
        return jsonify({"error": str(e)})


@app.route("/api/condition-orders/<order_id>", methods=["DELETE"])
def cancel_condition_order(order_id):
    """取消条件单"""
    try:
        # 简化实现
        logger.info(f"取消条件单：{order_id}")
        return jsonify({"success": True, "message": f"条件单已取消：{order_id}"})
    except Exception as e:
        logger.error(f"取消条件单失败：{e}")
        return jsonify({"error": str(e)})


@app.route("/api/grid-trading", methods=["GET"])
def get_grid_trading():
    """获取网格交易列表"""
    try:
        return jsonify({
            "grids": [],
            "count": 0,
        })
    except Exception as e:
        logger.error(f"获取网格交易失败：{e}")
        return jsonify({"error": str(e)})


@app.route("/api/grid-trading", methods=["POST"])
def create_grid_trading():
    """创建网格交易"""
    try:
        data = request.get_json()

        symbol = data.get("symbol", "BTC/USDT")
        lower_price = float(data.get("lower_price", 0))
        upper_price = float(data.get("upper_price", 0))
        grid_num = int(data.get("grid_num", 10))
        total_amount = float(data.get("total_amount", 100))

        # 验证参数
        if lower_price <= 0 or upper_price <= 0 or lower_price >= upper_price:
            return jsonify({"error": "价格区间设置无效"})
        if grid_num < 2 or grid_num > 100:
            return jsonify({"error": "网格数量必须在 2-100 之间"})
        if total_amount < 10:
            return jsonify({"error": "最小金额 10 USDT"})

        # 创建网格（简化实现）
        import uuid
        grid_id = str(uuid.uuid4())[:8]

        logger.info(
            f"创建网格交易：{grid_id} {symbol} "
            f"[{lower_price}-{upper_price}] {grid_num}格 {total_amount}USDT"
        )

        return jsonify({
            "success": True,
            "grid_id": grid_id,
            "message": f"网格交易已创建：{symbol}",
        })

    except Exception as e:
        logger.error(f"创建网格交易失败：{e}")
        return jsonify({"error": str(e)})


@app.route("/api/grid-trading/<grid_id>", methods=["DELETE"])
def stop_grid_trading(grid_id):
    """停止网格交易"""
    try:
        logger.info(f"停止网格交易：{grid_id}")
        return jsonify({"success": True, "message": f"网格交易已停止：{grid_id}"})
    except Exception as e:
        logger.error(f"停止网格交易失败：{e}")
        return jsonify({"error": str(e)})


@app.route("/api/grid-trading/<grid_id>/stats")
def get_grid_stats(grid_id):
    """获取网格交易统计"""
    try:
        # 简化实现
        return jsonify({
            "id": grid_id,
            "symbol": "BTC/USDT",
            "status": "running",
            "profit": 0.0,
            "buy_count": 0,
            "sell_count": 0,
        })
    except Exception as e:
        logger.error(f"获取网格统计失败：{e}")
        return jsonify({"error": str(e)})


# ============ 分析中心 API ============

@app.route("/api/analytics/performance")
def get_analytics_performance():
    """获取绩效分析"""
    try:
        from src.analytics.performance.metrics import PerformanceMetrics

        # 示例数据
        current_value = 12000.0
        days = 30
        daily_values = [10000 + i * 50 for i in range(30)]
        daily_returns = [0.005] * 30
        trades = [{"pnl": 100}, {"pnl": -50}, {"pnl": 200}, {"pnl": 150}]

        calculator = PerformanceMetrics(initial_capital=10000.0)
        metrics = calculator.calculate_all_metrics(
            current_value=current_value,
            days=days,
            daily_values=daily_values,
            daily_returns=daily_returns,
            trades=trades,
        )

        return jsonify(metrics)
    except Exception as e:
        logger.error(f"获取绩效分析失败：{e}")
        return jsonify({"error": str(e)})


@app.route("/api/analytics/trades")
def get_analytics_trades():
    """获取交易分析"""
    try:
        from src.analytics.trades.win_rate import TradeAnalyzer

        # 示例数据
        trades = [
            {"pnl": 100, "entry_time": "2024-01-01T10:00:00", "exit_time": "2024-01-01T15:00:00", "side": "buy", "symbol": "BTC/USDT"},
            {"pnl": -50, "entry_time": "2024-01-02T10:00:00", "exit_time": "2024-01-02T18:00:00", "side": "sell", "symbol": "BTC/USDT"},
            {"pnl": 200, "entry_time": "2024-01-03T10:00:00", "exit_time": "2024-01-03T14:00:00", "side": "buy", "symbol": "ETH/USDT"},
        ]

        analyzer = TradeAnalyzer()
        result = analyzer.analyze_trades(trades)

        return jsonify(result)
    except Exception as e:
        logger.error(f"获取交易分析失败：{e}")
        return jsonify({"error": str(e)})


@app.route("/api/analytics/capital-curve")
def get_analytics_capital_curve():
    """获取资金曲线分析"""
    try:
        from src.analytics.capital.curve import CapitalCurveAnalyzer

        # 示例数据
        daily_values = [
            {"date": f"2024-01-{i+1:02d}", "value": 10000 + i * 100}
            for i in range(30)
        ]

        analyzer = CapitalCurveAnalyzer(initial_capital=10000.0)
        result = analyzer.analyze_capital_curve(daily_values)

        return jsonify(result)
    except Exception as e:
        logger.error(f"获取资金曲线分析失败：{e}")
        return jsonify({"error": str(e)})


@app.route("/api/analytics/position")
def get_analytics_position():
    """获取持仓分析"""
    try:
        from src.analytics.position.analysis import PositionAnalyzer

        # 示例数据
        positions = [
            {"symbol": "BTC/USDT", "quantity": 0.1, "entry_price": 65000},
            {"symbol": "ETH/USDT", "quantity": 1.0, "entry_price": 3500},
        ]
        current_prices = {
            "BTC/USDT": 68000,
            "ETH/USDT": 3700,
        }

        analyzer = PositionAnalyzer()
        result = analyzer.analyze_positions(positions, current_prices)

        return jsonify(result)
    except Exception as e:
        logger.error(f"获取持仓分析失败：{e}")
        return jsonify({"error": str(e)})


@app.route("/api/analytics/strategy-comparison")
def get_analytics_strategy_comparison():
    """获取策略对比分析"""
    try:
        from src.analytics.strategy.comparison import StrategyComparator

        # 示例数据
        strategy_performance = {
            "SMA 交叉": {"pnl": 500, "return": 5.0, "sharpe": 1.2, "max_drawdown": 3.5, "win_rate": 55.0, "trades": 20},
            "MACD": {"pnl": 800, "return": 8.0, "sharpe": 1.5, "max_drawdown": 4.0, "win_rate": 60.0, "trades": 15},
            "布林带": {"pnl": 300, "return": 3.0, "sharpe": 0.8, "max_drawdown": 2.5, "win_rate": 48.0, "trades": 25},
        }

        comparator = StrategyComparator()
        result = comparator.compare_strategies(strategy_performance)

        return jsonify(result)
    except Exception as e:
        logger.error(f"获取策略对比失败：{e}")
        return jsonify({"error": str(e)})


# ============ WebSocket ============

# 定时推送任务
_state_push_task = None
_risk_push_task = None
_ticker_push_task = None

# 活跃 K 线订阅记录：key = "exchange:symbol:interval"
_active_kline_subscriptions: Dict[str, Dict] = {}


async def _periodic_state_push():
    """定期推送引擎状态到 WebSocket 客户端"""
    global engine
    while True:
        try:
            await asyncio.sleep(3)  # 3 秒推送一次状态
            if engine and engine.state == EngineState.RUNNING:
                status = engine.get_status()
                socketio.emit("engine_status", {
                    "state": status.get("state", "running"),
                    "uptime": get_uptime(),
                    "stats": status.get("stats", {}),
                })
        except Exception as e:
            logger.error(f"定期推送状态失败：{e}")


async def _periodic_risk_push():
    """定期推送风控数据到 WebSocket 客户端"""
    global engine
    while True:
        try:
            await asyncio.sleep(5)  # 5 秒推送一次风控
            if engine and engine.risk_manager:
                risk_stats = engine.risk_manager.get_stats()
                socketio.emit("risk_alert", risk_stats)
        except Exception as e:
            logger.error(f"定期推送风控失败：{e}")


async def _periodic_ticker_push():
    """定期推送行情数据到 WebSocket 客户端"""
    while True:
        try:
            await asyncio.sleep(4)  # 4 秒推送一次行情
            # 获取关注的交易对列表
            from src.data.models import SymbolWatchModel
            from src.data.database import get_db_session
            from sqlalchemy import select

            async with get_db_session() as db:
                result = await db.execute(select(SymbolWatchModel).where(SymbolWatchModel.is_active == True))
                symbols = result.scalars().all()

                for symbol_watch in symbols:
                    exchange_name = symbol_watch.exchange
                    symbol = symbol_watch.symbol

                    if engine and exchange_name in engine.exchanges:
                        exch = engine.exchanges[exchange_name]
                        if getattr(exch, 'connected', False):
                            try:
                                ticker = await exch.get_ticker(symbol)
                                socketio.emit("ticker_update", {
                                    "symbol": symbol,
                                    "exchange": exchange_name,
                                    "last": ticker.last,
                                    "bid": ticker.bid,
                                    "ask": ticker.ask,
                                    "high": ticker.high,
                                    "low": ticker.low,
                                    "volume": ticker.volume,
                                    "change": ticker.change,
                                })
                            except Exception as e:
                                logger.debug(f"推送行情失败 {symbol}: {e}")
        except Exception as e:
            logger.error(f"定期推送行情失败：{e}")


@socketio.on("connect")
def handle_connect(*args):
    """客户端连接"""
    logger.info(f"客户端连接：{request.sid}")
    emit("connected", {"message": "连接成功"})

    # 启动定期推送任务
    global _state_push_task, _risk_push_task, _ticker_push_task
    if _state_push_task is None or _state_push_task.done():
        _state_push_task = asyncio.create_task(_periodic_state_push())
    if _risk_push_task is None or _risk_push_task.done():
        _risk_push_task = asyncio.create_task(_periodic_risk_push())
    if _ticker_push_task is None or _ticker_push_task.done():
        _ticker_push_task = asyncio.create_task(_periodic_ticker_push())


#
@socketio.on("disconnect")
def handle_disconnect():
    """客户端断开"""
    logger.info(f"客户端断开：{request.sid}")


@socketio.on("start_engine")
def handle_start_engine():
    """启动引擎"""
    if engine is None:
        emit("error", {"message": "引擎未初始化"})
        return

    async def _start():
        try:
            await engine.start()
            # 发送引擎状态
            socketio.emit("engine_status", {"state": engine.state.value, "uptime": get_uptime()})
            # 发送交易所状态更新
            status = engine.get_status()
            socketio.emit("exchanges_update", {"exchanges": status.get("exchanges", {})})
            logger.info(f"引擎已启动，状态：{engine.state.value}")
        except Exception as e:
            logger.error(f"引擎启动失败：{e}")
            socketio.emit("error", {"message": f"引擎启动失败：{str(e)}"})

    run_async(_start())


@socketio.on("stop_engine")
def handle_stop_engine():
    """停止引擎"""
    if engine is None:
        emit("error", {"message": "引擎未初始化"})
        return

    async def _stop():
        try:
            await engine.stop()
            # 发送引擎状态
            socketio.emit("engine_status", {"state": engine.state.value, "uptime": get_uptime()})
            # 发送交易所状态更新（停止后交易所应全部断开）
            status = engine.get_status()
            socketio.emit("exchanges_update", {"exchanges": status.get("exchanges", {})})
            logger.info(f"引擎已停止，状态：{engine.state.value}")
        except Exception as e:
            logger.error(f"引擎停止失败：{e}")
            socketio.emit("error", {"message": f"引擎停止失败：{str(e)}"})

    run_async(_stop())


@socketio.on("disconnect_exchange")
def handle_disconnect_exchange(data):
    """断开交易所连接 - 只在引擎运行时允许"""
    if engine is None:
        emit("error", {"message": "引擎未初始化"})
        return

    # 检查引擎是否运行
    if engine.state != EngineState.RUNNING:
        emit("error", {"message": "引擎未运行，无法断开交易所"})
        return

    exchange_name = data.get("exchange")
    if exchange_name not in engine.exchanges:
        emit("error", {"message": f"交易所 {exchange_name} 未注册"})
        return

    async def _disconnect():
        try:
            await engine.exchanges[exchange_name].disconnect()
            socketio.emit("exchange_disconnected", {"exchange": exchange_name})
            logger.info(f"{exchange_name} 已断开连接")
        except Exception as e:
            logger.error(f"断开 {exchange_name} 失败：{e}")
            socketio.emit("error", {"message": f"断开连接失败：{str(e)}"})

    run_async(_disconnect())


@socketio.on("toggle_exchange")
def handle_toggle_exchange(data):
    """切换交易所连接状态（连接/断开）- 只在引擎运行时允许"""
    if engine is None:
        emit("error", {"message": "引擎未初始化"})
        return

    # 检查引擎是否运行
    if engine.state != EngineState.RUNNING:
        emit("error", {"message": "引擎未运行，无法切换交易所连接"})
        return

    exchange_name = data.get("exchange")
    if exchange_name not in engine.exchanges:
        emit("error", {"message": f"交易所 {exchange_name} 未注册"})
        return

    exch = engine.exchanges[exchange_name]
    is_connected = getattr(exch, 'connected', False)

    async def _toggle():
        try:
            if is_connected:
                await exch.disconnect()
                logger.info(f"{exchange_name} 已断开连接")
            else:
                await exch.connect()
                logger.info(f"{exchange_name} 已连接")

            # 刷新交易所状态
            status = engine.get_status()
            socketio.emit("exchanges_update", {"exchanges": status.get("exchanges", {})})
        except Exception as e:
            logger.error(f"切换 {exchange_name} 失败：{e}")
            socketio.emit("error", {"message": f"切换连接失败：{str(e)}"})

    run_async(_toggle())
#
#
# async def _refresh_exchanges_async():
#     """刷新交易所状态并推送"""
#     status = engine.get_status()
#     socketio.emit("exchanges_update", {"exchanges": status.get("exchanges", [])})


# ============ 启动 ============

async def init_engine():
    """初始化引擎（只创建对象，不连接交易所）"""
    global engine

    settings = get_settings()
    engine = TradingEngine()

    # 初始化风控管理器
    from src.risk.manager import RiskManager
    risk_manager = RiskManager()
    engine.set_risk_manager(risk_manager)
    logger.info('风控管理器已初始化')

    # 注册交易所（只创建对象，不连接）
    if settings.binance.enabled:
        from src.exchanges.binance import BinanceExchange
        binance = BinanceExchange()
        engine.register_exchange("binance", binance)
        logger.info("Binance 交易所已注册（未连接）")

    if settings.okx.enabled:
        from src.exchanges.okx import OKXExchange
        okx = OKXExchange()
        engine.register_exchange("okx", okx)
        logger.info("OKX 交易所已注册（未连接）")

    # 注册示例策略 - 定时数据采集
    engine.add_strategy("data_collector", DataCollectorStrategy())
    logger.info("数据采集策略已注册")

    # 注册 K 线采集策略
    engine.add_strategy("kline_collector", KLineCollectorStrategy())
    logger.info("K 线采集策略已注册")

    return engine


class KLineCollectorStrategy:
    """
    K 线采集策略：定时采集 K 线数据
    启动引擎后每 60 秒采集一次各周期的 K 线数据
    """
    def __init__(self):
        self.running = False
        self.task = None
        self.collect_interval = 60  # 60 秒采集一次
        self.intervals = ["1m", "5m", "15m", "1h", "4h", "1d"]  # 采集周期

    async def init(self):
        """策略初始化"""
        logger.info("K 线采集策略初始化完成")

    async def start(self, engine):
        """启动策略"""
        self.running = True
        self.task = asyncio.create_task(self._run(engine))
        logger.info(f"📊 K 线采集策略已启动（每{self.collect_interval}秒采集{len(self.intervals)}个周期）")

    async def stop(self):
        """停止策略"""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("📊 K 线采集策略已停止")

    async def _run(self, engine):
        """运行采集循环"""
        from src.data.kline_storage import get_kline_storage

        while self.running:
            try:
                # 获取关注的交易对列表
                from src.data.models import SymbolWatchModel
                from src.data.database import get_db_session
                from sqlalchemy import select

                async with get_db_session() as db:
                    result = await db.execute(select(SymbolWatchModel).where(SymbolWatchModel.is_active == True))
                    symbols = result.scalars().all()

                    for symbol_watch in symbols:
                        if not self.running:
                            break

                        exchange_name = symbol_watch.exchange
                        symbol = symbol_watch.symbol

                        if exchange_name not in engine.exchanges:
                            continue

                        exchange = engine.exchanges[exchange_name]
                        if not exchange.connected:
                            continue

                        # 采集各周期 K 线
                        for interval in self.intervals:
                            if not self.running:
                                break
                            try:
                                await self._fetch_and_store_kline(
                                    exchange, symbol, interval,
                                    get_kline_storage()
                                )
                            except Exception as e:
                                logger.debug(f"采集 K 线失败 {symbol} {interval}: {e}")

                # 等待下一次采集
                await asyncio.sleep(self.collect_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"K 线采集错误：{e}")
                await asyncio.sleep(5)

    async def _fetch_and_store_kline(self, exchange, symbol: str, interval: str, storage):
        """获取并存储 K 线"""
        from src.data.kline_collector import KLineCollector

        timeframe = KLineCollector.TIMEFRAME_MAP.get(interval, interval)
        klines_data = await exchange.fetch_ohlcv(symbol, timeframe, limit=100)

        if not klines_data:
            return

        klines = []
        for k in klines_data:
            klines.append({
                "open_time": datetime.fromtimestamp(k[0] / 1000),
                "open": k[1],
                "high": k[2],
                "low": k[3],
                "close": k[4],
                "volume": k[5],
                "quote_volume": k[6] if len(k) > 6 else 0.0,
                "trades_count": 0,
            })

        count = await storage.store_batch(symbol, interval, klines)
        logger.debug(f"存储 K 线 {symbol} {interval}: {count}/{len(klines)}")


class DataCollectorStrategy:
    """
    示例策略：定时采集行情数据
    启动引擎后每 10 秒采集一次关注列表的行情
    """
    def __init__(self):
        self.running = False
        self.task = None
        self.collect_interval = 10  # 10 秒

    async def init(self):
        """策略初始化"""
        logger.info("数据采集策略初始化完成")

    async def start(self, engine):
        """启动策略"""
        self.running = True
        self.task = asyncio.create_task(self._run(engine))
        logger.info(f"📊 数据采集策略已启动（每{self.collect_interval}秒采集一次）")

    async def stop(self):
        """停止策略"""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("📊 数据采集策略已停止")

    async def _run(self, engine):
        """运行采集循环"""
        while self.running:
            try:
                # 获取关注的交易对列表
                from src.data.models import SymbolWatchModel
                from src.data.database import get_db_session
                from sqlalchemy import select

                async with get_db_session() as db:
                    result = await db.execute(select(SymbolWatchModel).where(SymbolWatchModel.is_active == True))
                    symbols = result.scalars().all()

                    for symbol_watch in symbols:
                        if not self.running:
                            break

                        exchange_name = symbol_watch.exchange
                        symbol = symbol_watch.symbol

                        if exchange_name not in engine.exchanges:
                            continue

                        exchange = engine.exchanges[exchange_name]
                        if not exchange.connected:
                            continue

                        try:
                            # 获取行情
                            ticker = await exchange.get_ticker(symbol)
                            logger.debug(f"采集行情：{symbol} = {ticker.last}")

                            # 保存到数据库
                            from src.data.models import TickerModel
                            db.add(TickerModel(
                                exchange=exchange_name,
                                symbol=symbol,
                                price=ticker.last,
                                high_24h=ticker.high,
                                low_24h=ticker.low,
                                volume_24h=ticker.volume,
                                quote_volume_24h=ticker.quote_volume,
                            ))
                            await db.commit()

                            # 推送到 WebSocket
                            socketio.emit("ticker_update", {
                                "symbol": symbol,
                                "exchange": exchange_name,
                                "last": ticker.last,
                                "bid": ticker.bid,
                                "ask": ticker.ask,
                                "high": ticker.high,
                                "low": ticker.low,
                                "volume": ticker.volume,
                                "change": ticker.change,
                            })

                        except Exception as e:
                            logger.debug(f"采集 {symbol} 失败：{e}")

                # 等待下一次采集
                await asyncio.sleep(self.collect_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"数据采集错误：{e}")
                await asyncio.sleep(5)


def create_app(trading_engine: TradingEngine = None):
    """创建应用"""
    global engine
    engine = trading_engine
    return app


def run_server(host: str = "0.0.0.0", port: int = None):
    """运行服务器"""
    setup_logging()

    # 初始化引擎 - 使用 asyncio.run 直接运行
    logger.info("初始化交易引擎...")
    logger.debug("Debug 模式已启用")

    async def _init():
        return await init_engine()

    engine = asyncio.run(_init())
    globals()['engine'] = engine

    # 使用 PORT 环境变量或默认的 5001 端口
    if port is None:
        port = SERVER_PORT

    logger.info(f"Web 服务器启动：http://{host}:{port}")
    logger.info("使用 Werkzeug 开发服务器，建议生产环境使用 gunicorn")
    logger.debug(f"日志级别：DEBUG")

    # 使用 threaded=True 启用多线程处理
    if socketio:
        # SocketIO 自带 threaded 模式，启用 debug
        socketio.run(app, host=host, port=port, debug=True, allow_unsafe_werkzeug=True, log_output=True)
    else:
        # 使用 threaded mode with debug
        from werkzeug.serving import run_simple
        run_simple(host, port, app, threaded=True, use_reloader=True, use_debugger=True)


if __name__ == "__main__":
    run_server()
