"""
完整功能测试脚本（需要 API Key）
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import load_settings
from src.core.logger import setup_logging
from src.core.engine import TradingEngine
from src.exchanges.binance import BinanceExchange
from src.exchanges.okx import OKXExchange
from src.strategies.sma_strategy import SMAStrategy
from src.strategies.base import StrategyConfig
from src.risk.manager import RiskManager


async def test_with_api():
    """测试需要 API Key 的功能"""
    setup_logging()
    settings = load_settings()
    
    print("\n" + "=" * 60)
    print("Crypto Quant Trader - 完整功能测试")
    print("=" * 60)
    
    # 检查 API Key 配置
    print("\n[配置检查]")
    
    if settings.binance.api_key and settings.binance.api_key != "YOUR_BINANCE_API_KEY":
        print(f"  Binance API Key: {settings.binance.api_key[:8]}...")
    else:
        print("  Binance API Key: [未配置]")
    
    if settings.okx.api_key and settings.okx.api_key != "YOUR_OKX_API_KEY":
        print(f"  OKX API Key: {settings.okx.api_key[:8]}...")
    else:
        print("  OKX API Key: [未配置]")
    
    print(f"  代理: {settings.proxy.http if settings.proxy.enabled else '未启用'}")
    print(f"  运行模式: {settings.mode}")
    
    # ============ 测试账户余额 ============
    print("\n[账户余额测试]")
    
    # Binance
    if settings.binance.api_key and settings.binance.api_key != "YOUR_BINANCE_API_KEY":
        binance = BinanceExchange()
        try:
            await binance.connect()
            balance = await binance.get_balance()
            print(f"  Binance 余额:")
            for currency, amount in balance.items():
                print(f"    {currency}: {amount}")
        except Exception as e:
            print(f"  Binance: [ERROR] {e}")
        finally:
            await binance.disconnect()
    else:
        print("  Binance: [跳过] API Key 未配置")
    
    # OKX
    if settings.okx.api_key and settings.okx.api_key != "YOUR_OKX_API_KEY":
        okx = OKXExchange()
        try:
            await okx.connect()
            balance = await okx.get_balance()
            print(f"  OKX 余额:")
            for currency, amount in balance.items():
                print(f"    {currency}: {amount}")
        except Exception as e:
            print(f"  OKX: [ERROR] {e}")
        finally:
            await okx.disconnect()
    else:
        print("  OKX: [跳过] API Key 未配置")
    
    # ============ 测试策略 ============
    print("\n[策略测试]")
    
    binance = BinanceExchange()
    try:
        await binance.connect()
        
        config = StrategyConfig(
            name="SMA_BTC",
            symbol="BTC/USDT",
            timeframe="1h",
            params={
                "fast_period": 10,
                "slow_period": 30,
            }
        )
        
        strategy = SMAStrategy(config)
        strategy.exchange = binance
        await strategy.init()
        
        indicators = strategy.get_indicators()
        print(f"  策略: {strategy.name}")
        print(f"  快线 MA{strategy.fast_period}: {indicators.get('fast_ma', 0):.2f}")
        print(f"  慢线 MA{strategy.slow_period}: {indicators.get('slow_ma', 0):.2f}")
        print(f"  趋势: {indicators.get('trend', 'N/A')}")
        
        signal = await strategy.generate_signal()
        if signal:
            print(f"  信号: {signal['side']} - {signal['reason']}")
        else:
            print(f"  信号: 无")
        
    except Exception as e:
        print(f"  [ERROR] {e}")
    finally:
        await binance.disconnect()
    
    # ============ 测试风控 ============
    print("\n[风控测试]")
    
    risk = RiskManager()
    print(f"  最大仓位: {risk.settings.max_position} USDT")
    print(f"  每日最大亏损: {risk.settings.max_daily_loss} USDT")
    print(f"  止损比例: {risk.settings.stop_loss_percent}%")
    print(f"  止盈比例: {risk.settings.take_profit_percent}%")
    
    # ============ 测试引擎 ============
    print("\n[引擎测试]")
    
    engine = TradingEngine()
    print(f"  状态: {engine.state.value}")
    print(f"  交易所: {list(engine.exchanges.keys())}")
    print(f"  策略: {list(engine.strategies.keys())}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_with_api())
