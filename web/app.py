"""
Web 界面 - Flask 应用
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from loguru import logger

from src.core.engine import TradingEngine, EngineState
from src.core.config import get_settings, load_settings
from src.core.logger import setup_logging
from src.exchanges.base import OrderSide, OrderType


# 创建应用
app = Flask(__name__)
app.config["SECRET_KEY"] = "crypto-quant-trader-secret"
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# 全局引擎实例
engine: TradingEngine = None


def run_async(coro):
    """在同步环境中运行异步函数"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ============ REST API ============

@app.route("/")
def index():
    """首页"""
    return render_template("index.html")


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
    
    async def _get_balance():
        balances = {}
        for name, exchange in engine.exchanges.items():
            try:
                balance = await exchange.get_balance()
                balances[name] = balance
            except Exception as e:
                logger.error(f"获取 {name} 余额失败: {e}")
                balances[name] = {"error": str(e)}
        return balances
    
    balances = run_async(_get_balance())
    return jsonify(balances)


@app.route("/api/ticker/<exchange>/<symbol>")
def get_ticker(exchange, symbol):
    """获取行情"""
    if engine is None:
        return jsonify({"error": "引擎未初始化"})
    
    if exchange not in engine.exchanges:
        return jsonify({"error": f"交易所 {exchange} 未注册"})
    
    async def _get_ticker():
        ex = engine.exchanges[exchange]
        ticker = await ex.get_ticker(symbol)
        return {
            "symbol": ticker.symbol,
            "last": ticker.last,
            "bid": ticker.bid,
            "ask": ticker.ask,
            "high": ticker.high,
            "low": ticker.low,
            "volume": ticker.volume,
            "timestamp": ticker.timestamp.isoformat(),
        }
    
    try:
        ticker = run_async(_get_ticker())
        return jsonify(ticker)
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/order", methods=["POST"])
def create_order():
    """创建订单"""
    if engine is None:
        return jsonify({"error": "引擎未初始化"})

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
    amount = data["amount"]
    price = data.get("price")

    # 验证交易所
    if exchange_name not in engine.exchanges:
        return jsonify({"error": f"交易所 {exchange_name} 未连接"}), 400

    # 验证参数
    if amount <= 0:
        return jsonify({"error": "数量必须大于 0"}), 400

    if order_type == "limit" and price is None:
        return jsonify({"error": "限价单需要指定价格"}), 400

    # 映射订单类型
    type_map = {
        "market": OrderType.MARKET,
        "limit": OrderType.LIMIT,
        "stop_loss": OrderType.STOP_LOSS,
        "stop_loss_limit": OrderType.STOP_LOSS_LIMIT,
        "take_profit": OrderType.TAKE_PROFIT,
        "take_profit_limit": OrderType.TAKE_PROFIT_LIMIT,
    }

    if order_type not in type_map:
        return jsonify({"error": f"不支持的订单类型：{order_type}"}), 400

    # 映射订单方向
    side_map = {
        "buy": OrderSide.BUY,
        "sell": OrderSide.SELL,
    }

    if side not in side_map:
        return jsonify({"error": f"不支持的订单方向：{side}"}), 400

    async def _create_order():
        exchange = engine.exchanges[exchange_name]
        order = await exchange.create_order(
            symbol=symbol,
            side=side_map[side],
            order_type=type_map[order_type],
            amount=amount,
            price=price,
        )
        return order

    try:
        order = run_async(_create_order())

        # 发送 WebSocket 通知
        socketio.emit("order_created", {
            "id": order.id,
            "symbol": order.symbol,
            "side": order.side.value,
            "type": order.type.value,
            "amount": order.amount,
            "price": order.price,
            "status": order.status.value,
        })

        logger.info(f"订单创建成功：{order.id} {side} {amount} {symbol}")

        return jsonify({
            "message": f"订单创建成功",
            "order": {
                "id": order.id,
                "symbol": order.symbol,
                "side": order.side.value,
                "type": order.type.value,
                "amount": order.amount,
                "price": order.price,
                "status": order.status.value,
                "filled": order.filled,
                "remaining": order.remaining,
                "cost": order.cost,
            }
        })

    except Exception as e:
        logger.error(f"订单创建失败：{e}")
        return jsonify({"error": f"订单创建失败：{str(e)}"}), 500


@app.route("/api/risk")
def get_risk():
    """获取风控状态"""
    if engine is None or engine.risk_manager is None:
        return jsonify({"error": "风控管理器未设置"})
    
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


# ============ WebSocket ============

@socketio.on("connect")
def handle_connect():
    """客户端连接"""
    logger.info(f"客户端连接: {request.sid}")
    emit("connected", {"message": "连接成功"})


@socketio.on("disconnect")
def handle_disconnect():
    """客户端断开"""
    logger.info(f"客户端断开: {request.sid}")


@socketio.on("start_engine")
def handle_start_engine():
    """启动引擎"""
    if engine is None:
        emit("error", {"message": "引擎未初始化"})
        return
    
    async def _start():
        try:
            await engine.start()
            socketio.emit("engine_status", {"state": engine.state.value})
            logger.info(f"引擎已启动，状态: {engine.state.value}")
        except Exception as e:
            logger.error(f"引擎启动失败: {e}")
            socketio.emit("error", {"message": f"引擎启动失败: {str(e)}"})
    
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
            socketio.emit("engine_status", {"state": engine.state.value})
            logger.info(f"引擎已停止，状态: {engine.state.value}")
        except Exception as e:
            logger.error(f"引擎停止失败: {e}")
            socketio.emit("error", {"message": f"引擎停止失败: {str(e)}"})
    
    run_async(_stop())


@socketio.on("disconnect_exchange")
def handle_disconnect_exchange(data):
    """断开交易所连接"""
    if engine is None:
        emit("error", {"message": "引擎未初始化"})
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
            # 刷新交易所列表
            await _refresh_exchanges_async()
        except Exception as e:
            logger.error(f"断开 {exchange_name} 失败: {e}")
            socketio.emit("error", {"message": f"断开连接失败: {str(e)}"})
    
    run_async(_disconnect())


@socketio.on("connect_exchange")
def handle_connect_exchange(data):
    """连接交易所"""
    if engine is None:
        emit("error", {"message": "引擎未初始化"})
        return
    
    exchange_name = data.get("exchange")
    if exchange_name not in engine.exchanges:
        emit("error", {"message": f"交易所 {exchange_name} 未注册"})
        return
    
    async def _connect():
        try:
            await engine.exchanges[exchange_name].connect()
            socketio.emit("exchange_connected", {"exchange": exchange_name})
            logger.info(f"{exchange_name} 已连接")
            # 刷新交易所列表
            await _refresh_exchanges_async()
        except Exception as e:
            logger.error(f"连接 {exchange_name} 失败: {e}")
            socketio.emit("error", {"message": f"连接失败: {str(e)}"})
    
    run_async(_connect())


async def _refresh_exchanges_async():
    """刷新交易所状态并推送"""
    status = engine.get_status()
    socketio.emit("exchanges_update", {"exchanges": status.get("exchanges", [])})


# ============ 启动 ============

async def init_engine():
    """初始化引擎"""
    global engine
    
    settings = get_settings()
    engine = TradingEngine()
    
    # 注册交易所
    if settings.binance.enabled:
        from src.exchanges.binance import BinanceExchange
        binance = BinanceExchange()
        engine.register_exchange("binance", binance)
        logger.info("Binance 交易所已注册")
    
    if settings.okx.enabled:
        from src.exchanges.okx import OKXExchange
        okx = OKXExchange()
        engine.register_exchange("okx", okx)
        logger.info("OKX 交易所已注册")
    
    # 连接交易所
    for name, exchange in engine.exchanges.items():
        try:
            await exchange.connect()
            logger.info(f"{name} 已连接")
        except Exception as e:
            logger.error(f"{name} 连接失败: {e}")
    
    return engine


def create_app(trading_engine: TradingEngine = None):
    """创建应用"""
    global engine
    engine = trading_engine
    return app


def run_server(host: str = "0.0.0.0", port: int = 5000):
    """运行服务器"""
    setup_logging()
    
    # 初始化引擎
    logger.info("初始化交易引擎...")
    run_async(init_engine())
    
    logger.info(f"Web 服务器启动: http://{host}:{port}")
    socketio.run(app, host=host, port=port, debug=True, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    run_server()
