"""
测试网运行脚本
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import load_settings
from src.core.logger import setup_logging
from src.core.engine import TradingEngine
from src.exchanges.binance import BinanceExchange
from src.exchanges.okx import OKXExchange
from src.strategies.sma_strategy import SMAStrategy
from src.strategies.base import StrategyConfig
from src.risk.manager import RiskManager

from loguru import logger


async def test_connection():
    """测试交易所连接"""
    setup_logging()
    settings = load_settings()
    
    logger.info("=" * 50)
    logger.info("交易所连接测试")
    logger.info("=" * 50)
    
    # 测试 Binance
    if settings.binance.enabled:
        logger.info("\n📡 测试 Binance 连接...")
        binance = BinanceExchange()
        
        try:
            await binance.connect()
            
            # 获取行情
            ticker = await binance.get_ticker("BTC/USDT")
            logger.info(f"BTC/USDT 行情: ${ticker.last:.2f}")
            
            # 获取K线
            klines = await binance.get_klines("BTC/USDT", "1h", 5)
            logger.info(f"获取到 {len(klines)} 根K线")
            
            # 获取余额
            balance = await binance.get_balance()
            logger.info(f"账户余额: {balance}")
            
            logger.info("✅ Binance 连接成功！")
            
        except Exception as e:
            logger.error(f"❌ Binance 连接失败: {e}")
        finally:
            await binance.disconnect()
    
    # 测试 OKX
    if settings.okx.enabled:
        logger.info("\n📡 测试 OKX 连接...")
        okx = OKXExchange()
        
        try:
            await okx.connect()
            
            # 获取行情
            ticker = await okx.get_ticker("BTC/USDT")
            logger.info(f"BTC/USDT 行情: ${ticker.last:.2f}")
            
            # 获取K线
            klines = await okx.get_klines("BTC/USDT", "1h", 5)
            logger.info(f"获取到 {len(klines)} 根K线")
            
            # 获取余额
            balance = await okx.get_balance()
            logger.info(f"账户余额: {balance}")
            
            logger.info("✅ OKX 连接成功！")
            
        except Exception as e:
            logger.error(f"❌ OKX 连接失败: {e}")
        finally:
            await okx.disconnect()


async def test_strategy():
    """测试策略"""
    setup_logging()
    settings = load_settings()
    
    logger.info("\n" + "=" * 50)
    logger.info("策略测试")
    logger.info("=" * 50)
    
    # 创建策略配置
    config = StrategyConfig(
        name="SMA_BTC",
        symbol="BTC/USDT",
        timeframe="1h",
        params={
            "fast_period": 10,
            "slow_period": 30,
        }
    )
    
    # 创建策略实例
    strategy = SMAStrategy(config)
    
    # 连接交易所
    binance = BinanceExchange()
    await binance.connect()
    strategy.exchange = binance
    
    # 初始化策略
    await strategy.init()
    
    # 获取当前指标
    indicators = strategy.get_indicators()
    logger.info(f"当前指标: {indicators}")
    
    # 生成信号
    signal = await strategy.generate_signal()
    if signal:
        logger.info(f"交易信号: {signal}")
    else:
        logger.info("当前无交易信号")
    
    await binance.disconnect()
    logger.info("✅ 策略测试完成！")


async def test_engine():
    """测试交易引擎"""
    setup_logging()
    settings = load_settings()
    
    logger.info("\n" + "=" * 50)
    logger.info("交易引擎测试")
    logger.info("=" * 50)
    
    # 创建引擎
    engine = TradingEngine()
    
    # 注册交易所
    if settings.binance.enabled:
        binance = BinanceExchange()
        engine.register_exchange("binance", binance)
    
    if settings.okx.enabled:
        okx = OKXExchange()
        engine.register_exchange("okx", okx)
    
    # 注册策略
    config = StrategyConfig(
        name="SMA_BTC",
        symbol="BTC/USDT",
        timeframe="1h",
    )
    strategy = SMAStrategy(config)
    engine.register_strategy("sma_btc", strategy)
    
    # 设置风控
    risk_manager = RiskManager()
    engine.set_risk_manager(risk_manager)
    
    # 启动引擎
    await engine.start()
    
    # 运行 10 秒
    logger.info("引擎运行 10 秒...")
    await asyncio.sleep(10)
    
    # 停止引擎
    await engine.stop()
    
    # 打印状态
    logger.info(f"引擎状态: {engine.get_status()}")
    logger.info("✅ 引擎测试完成！")


async def main():
    """主函数"""
    print("\n" + "=" * 50)
    print("Crypto Quant Trader - 测试网测试")
    print("=" * 50)
    print("\n请选择测试:")
    print("1. 测试交易所连接")
    print("2. 测试策略")
    print("3. 测试交易引擎")
    print("4. 全部测试")
    print("0. 退出")
    
    choice = input("\n请输入选项: ").strip()
    
    if choice == "1":
        await test_connection()
    elif choice == "2":
        await test_strategy()
    elif choice == "3":
        await test_engine()
    elif choice == "4":
        await test_connection()
        await test_strategy()
        await test_engine()
    elif choice == "0":
        print("退出")
    else:
        print("无效选项")


if __name__ == "__main__":
    asyncio.run(main())
