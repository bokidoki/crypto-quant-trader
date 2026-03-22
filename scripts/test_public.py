"""
简化测试脚本 - 只测试公开 API（无需 API Key）
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import load_settings
from src.core.logger import setup_logging
from src.exchanges.binance import BinanceExchange
from src.exchanges.okx import OKXExchange

from loguru import logger


async def test_public_api():
    """测试公开 API"""
    setup_logging()
    settings = load_settings()
    
    print("\n" + "=" * 60)
    print("Crypto Quant Trader - 公开 API 测试")
    print("=" * 60)
    
    # ============ 测试 Binance ============
    print("\n[Binance 测试]")
    binance = BinanceExchange()
    
    try:
        await binance.connect()
        print("  连接成功")
        
        # 获取行情
        ticker = await binance.get_ticker("BTC/USDT")
        print(f"  BTC/USDT: ${ticker.last:.2f}")
        print(f"  24h High: ${ticker.high:.2f}")
        print(f"  24h Low: ${ticker.low:.2f}")
        print(f"  24h Volume: {ticker.volume:,.0f}")
        
        # 获取K线
        klines = await binance.get_klines("BTC/USDT", "1h", 5)
        print(f"  获取到 {len(klines)} 根K线")
        for i, k in enumerate(klines[-3:], 1):
            print(f"    [{i}] {k.timestamp.strftime('%Y-%m-%d %H:%M')} O:{k.open:.2f} H:{k.high:.2f} L:{k.low:.2f} C:{k.close:.2f}")
        
        print("  [OK] Binance 公开 API 正常")
        
    except Exception as e:
        print(f"  [ERROR] Binance: {e}")
    finally:
        await binance.disconnect()
    
    # ============ 测试 OKX ============
    print("\n[OKX 测试]")
    okx = OKXExchange()
    
    try:
        await okx.connect()
        print("  连接成功")
        
        # 获取行情
        ticker = await okx.get_ticker("BTC/USDT")
        print(f"  BTC/USDT: ${ticker.last:.2f}")
        print(f"  24h High: ${ticker.high:.2f}")
        print(f"  24h Low: ${ticker.low:.2f}")
        print(f"  24h Volume: {ticker.volume:,.0f}")
        
        # 获取K线
        klines = await okx.get_klines("BTC/USDT", "1h", 5)
        print(f"  获取到 {len(klines)} 根K线")
        for i, k in enumerate(klines[-3:], 1):
            print(f"    [{i}] {k.timestamp.strftime('%Y-%m-%d %H:%M')} O:{k.open:.2f} H:{k.high:.2f} L:{k.low:.2f} C:{k.close:.2f}")
        
        print("  [OK] OKX 公开 API 正常")
        
    except Exception as e:
        print(f"  [ERROR] OKX: {e}")
    finally:
        await okx.disconnect()
    
    # ============ 测试其他币种 ============
    print("\n[其他币种测试]")
    binance = BinanceExchange()
    
    try:
        await binance.connect()
        
        symbols = ["ETH/USDT", "SOL/USDT", "DOGE/USDT"]
        for symbol in symbols:
            try:
                ticker = await binance.get_ticker(symbol)
                print(f"  {symbol}: ${ticker.last:.4f}")
            except Exception as e:
                print(f"  {symbol}: [ERROR] {e}")
        
    except Exception as e:
        print(f"  [ERROR] {e}")
    finally:
        await binance.disconnect()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_public_api())
