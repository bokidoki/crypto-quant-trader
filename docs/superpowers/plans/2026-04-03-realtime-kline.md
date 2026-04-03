# 实时 K 线推送功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 K 线图表的实时数据推送功能，采用混合模式（历史数据从 API 加载 + WebSocket 实时推送增量数据）

**Architecture:** 
- 前端通过 REST API 加载历史 K 线数据
- 前端通过 WebSocket 向后端订阅实时 K 线
- 后端调用交易所 WebSocket 订阅 K 线，通过回调接收实时数据
- 后端通过 SocketIO 将 K 线数据推送到前端

**Tech Stack:** Flask-SocketIO, Binance/OKX WebSocket, Lightweight Charts, JavaScript, Python

---

## File Structure

### 修改的文件

| 文件 | 职责 |
|------|------|
| `web/app.py` | 添加 K 线订阅/取消订阅的 WebSocket 处理器，K 线推送逻辑 |
| `web/templates/index.html` | 添加前端 K 线订阅管理，WebSocket 事件处理，图表增量更新 |

### 关键设计决策

- 不创建新文件，复用现有 WebSocket 基础设施
- K 线订阅状态保存在内存中 (`_active_kline_subscriptions`)
- 使用交易所已有的 `subscribe_klines` 和 `unsubscribe_klines` 方法
- 前端在 `loadKlineChart()` 中自动发起订阅，切换周期时自动更新

---

### Task 1: 后端添加 K 线订阅管理数据结构

**Files:**
- Modify: `web/app.py:1079-1083`

- [ ] **Step 1: 添加活跃 K 线订阅记录字典**

在 `web/app.py` 文件第 1079 行附近，添加全局变量：

```python
# 活跃 K 线订阅记录：key = "exchange:symbol:interval"
_active_kline_subscriptions: Dict[str, Dict] = {}
```

- [ ] **Step 2: 确认导入 Dict 类型**

检查文件开头是否有 `from typing import Dict`，如果没有则添加：

```python
from typing import Dict, List, Optional, Callable, Any
```

- [ ] **Step 3: 提交**

```bash
git add web/app.py
git commit -m "refactor: 添加 K 线订阅管理数据结构"
```

---

### Task 2: 后端添加取消订阅辅助函数

**Files:**
- Modify: `web/app.py:1150-1153` (在 `_periodic_ticker_push` 函数之后)

- [ ] **Step 1: 添加 `_unsubscribe_kline` 辅助函数**

在 `_periodic_ticker_push` 函数之后添加：

```python
async def _unsubscribe_kline(sub_key: str):
    """取消 K 线订阅"""
    if sub_key not in _active_kline_subscriptions:
        return
    
    sub = _active_kline_subscriptions[sub_key]
    exchange_name = sub["exchange"]
    symbol = sub["symbol"]
    interval = sub["interval"]
    
    if engine and exchange_name in engine.exchanges:
        exch = engine.exchanges[exchange_name]
        try:
            await exch.unsubscribe_klines(symbol, interval)
            logger.info(f"K 线已取消订阅：{sub_key}")
        except Exception as e:
            logger.error(f"取消 K 线订阅失败 {sub_key}: {e}")
    
    del _active_kline_subscriptions[sub_key]
```

- [ ] **Step 2: 提交**

```bash
git add web/app.py
git commit -m "feat: 添加 K 线取消订阅辅助函数"
```

---

### Task 3: 后端添加订阅 K 线 WebSocket 处理器

**Files:**
- Modify: `web/app.py:1168-1170` (在 `handle_connect` 函数之后)

- [ ] **Step 1: 添加 `handle_subscribe_klines` 处理器**

在 `handle_connect` 函数之后添加：

```python
@socketio.on("subscribe_klines")
def handle_subscribe_klines(data):
    """处理 K 线订阅请求"""
    from loguru import logger
    
    exchange_name = data.get("exchange", "binance")
    symbol = data.get("symbol")
    interval = data.get("interval")
    
    if not symbol or not interval:
        emit("error", {"message": "参数错误：需要 symbol 和 interval"})
        return
    
    # 检查引擎
    if engine is None:
        emit("error", {"message": "引擎未初始化"})
        return
    
    # 检查交易所
    if exchange_name not in engine.exchanges:
        emit("error", {"message": f"交易所 {exchange_name} 不可用"})
        return
    
    exch = engine.exchanges[exchange_name]
    if not getattr(exch, 'connected', False):
        emit("error", {"message": f"交易所 {exchange_name} 未连接"})
        return
    
    # 生成订阅 key
    sub_key = f"{exchange_name}:{symbol}:{interval}"
    
    # 如果已订阅，先取消
    if sub_key in _active_kline_subscriptions:
        asyncio.create_task(_unsubscribe_kline(sub_key))
    
    # 创建回调函数
    async def kline_callback(kline):
        try:
            socketio.emit("kline_update", {
                "exchange": exchange_name,
                "symbol": symbol,
                "interval": interval,
                "time": int(kline.timestamp.timestamp() * 1000),
                "open": kline.open,
                "high": kline.high,
                "low": kline.low,
                "close": kline.close,
                "volume": kline.volume,
                "is_closed": kline.is_closed,
            })
        except Exception as e:
            logger.error(f"推送 K 线失败：{e}")
    
    # 订阅交易所 K 线
    try:
        loop = asyncio.get_event_loop()
        future = asyncio.run_coroutine_threadsafe(
            exch.subscribe_klines(symbol, interval, kline_callback),
            loop
        )
        future.result(timeout=5)
        
        _active_kline_subscriptions[sub_key] = {
            "exchange": exchange_name,
            "symbol": symbol,
            "interval": interval,
            "callback": kline_callback,
        }
        
        logger.info(f"K 线订阅成功：{sub_key}")
        emit("kline_subscribed", {
            "exchange": exchange_name,
            "symbol": symbol,
            "interval": interval,
        })
    except Exception as e:
        logger.error(f"K 线订阅失败：{e}")
        emit("error", {"message": f"订阅失败：{str(e)}"})
```

- [ ] **Step 2: 提交**

```bash
git add web/app.py
git commit -m "feat: 添加 K 线订阅 WebSocket 处理器"
```

---

### Task 4: 后端添加取消订阅 WebSocket 处理器

**Files:**
- Modify: `web/app.py` (在 `handle_subscribe_klines` 之后)

- [ ] **Step 1: 添加 `handle_unsubscribe_klines` 处理器**

在 `handle_subscribe_klines` 函数之后添加：

```python
@socketio.on("unsubscribe_klines")
def handle_unsubscribe_klines(data):
    """处理 K 线取消订阅请求"""
    exchange_name = data.get("exchange", "binance")
    symbol = data.get("symbol")
    interval = data.get("interval")
    
    if not symbol or not interval:
        emit("error", {"message": "参数错误"})
        return
    
    sub_key = f"{exchange_name}:{symbol}:{interval}"
    asyncio.create_task(_unsubscribe_kline(sub_key))
```

- [ ] **Step 2: 提交**

```bash
git add web/app.py
git commit -m "feat: 添加 K 线取消订阅 WebSocket 处理器"
```

---

### Task 5: 前端添加 K 线订阅管理变量和函数

**Files:**
- Modify: `web/templates/index.html:2220-2225` (在 K 线图表变量声明附近)

- [ ] **Step 1: 添加 K 线订阅状态变量**

在 `currentKlineInterval` 变量之后添加：

```javascript
let currentKlineSubscription = null;  // 当前 K 线订阅状态
```

- [ ] **Step 2: 添加 subscribeKlines 函数**

在 `loadKlineChart` 函数之后添加：

```javascript
function subscribeKlines(symbol, interval) {
    console.log('[DEBUG] 订阅 K 线:', symbol, interval);
    
    // 先取消旧订阅
    if (currentKlineSubscription) {
        console.log('[DEBUG] 取消旧订阅:', currentKlineSubscription);
        socket.emit('unsubscribe_klines', currentKlineSubscription);
    }
    
    // 获取当前交易所（从 UI 或默认）
    const exchange = document.getElementById('tickerExchangeSelector') 
        ? document.getElementById('tickerExchangeSelector').value 
        : 'binance';
    
    // 创建新订阅
    currentKlineSubscription = {
        exchange: exchange,
        symbol: symbol,
        interval: interval
    };
    
    socket.emit('subscribe_klines', currentKlineSubscription);
}
```

- [ ] **Step 3: 添加 unsubscribeKlines 函数**

在 `subscribeKlines` 函数之后添加：

```javascript
function unsubscribeKlines() {
    if (currentKlineSubscription) {
        console.log('[DEBUG] 取消 K 线订阅:', currentKlineSubscription);
        socket.emit('unsubscribe_klines', currentKlineSubscription);
        currentKlineSubscription = null;
    }
}
```

- [ ] **Step 4: 提交**

```bash
git add web/templates/index.html
git commit -m "feat: 添加 K 线订阅管理函数"
```

---

### Task 6: 前端添加 K 线 WebSocket 事件处理器

**Files:**
- Modify: `web/templates/index.html:955-960` (在 socket.on('exchanges_update') 之后)

- [ ] **Step 1: 添加 kline_subscribed 事件处理器**

在 `socket.on('exchanges_update')` 之后添加：

```javascript
socket.on('kline_subscribed', (data) => {
    console.log('[DEBUG] K 线已订阅:', data);
    addLog('info', `K 线已订阅：${data.symbol} ${data.interval}`);
});
```

- [ ] **Step 2: 添加 kline_update 事件处理器**

在 `kline_subscribed` 处理器之后添加：

```javascript
socket.on('kline_update', (data) => {
    console.log('[DEBUG] 收到 K 线更新:', data);
    updateKlineChart(data);
});
```

- [ ] **Step 3: 提交**

```bash
git add web/templates/index.html
git commit -m "feat: 添加 K 线 WebSocket 事件处理器"
```

---

### Task 7: 前端添加 K 线图表增量更新函数

**Files:**
- Modify: `web/templates/index.html:2318-2320` (在 loadKlineChart 函数之后)

- [ ] **Step 1: 添加 updateKlineChart 函数**

在 `loadKlineChart` 函数之后添加：

```javascript
function updateKlineChart(kline) {
    if (!klineSeries) {
        console.log('[DEBUG] K 线图表未初始化');
        return;
    }
    
    // 转换为 Lightweight Charts 格式（秒级时间戳）
    const candleData = {
        time: kline.time / 1000,
        open: kline.open,
        high: kline.high,
        low: kline.low,
        close: kline.close,
    };
    
    // 使用 update 方法进行增量更新
    klineSeries.update(candleData);
    
    // 未闭合 K 线可以通过颜色区分（可选）
    // Lightweight Charts 不直接支持单根 K 线的样式定制
    // 但可以通过日志观察状态
    if (!kline.is_closed) {
        console.log('[DEBUG] 未闭合 K 线更新:', candleData);
    } else {
        console.log('[DEBUG] 已闭合 K 线:', candleData);
    }
}
```

- [ ] **Step 2: 提交**

```bash
git add web/templates/index.html
git commit -m "feat: 添加 K 线图表增量更新函数"
```

---

### Task 8: 前端修改 loadKlineChart 调用订阅

**Files:**
- Modify: `web/templates/index.html:2279-2318` (loadKlineChart 函数)

- [ ] **Step 1: 修改 loadKlineChart 在加载历史数据后发起订阅**

将 `loadKlineChart` 函数修改为：

```javascript
async function loadKlineChart() {
    if (!klineChart || !klineSeries) {
        initKlineChart();
    }

    const symbol = document.getElementById('klineSymbolSelector').value;
    const interval = currentKlineInterval;

    currentKlineSymbol = symbol;

    try {
        const response = await fetch(`/api/klines?symbol=${encodeURIComponent(symbol)}&interval=${interval}&limit=200`);
        const data = await response.json();

        if (data.klines && data.klines.length > 0) {
            // 转换为 TradingView 格式
            const klineData = data.klines.map(k => ({
                time: k.time / 1000, // 转换为秒级时间戳
                open: k.open,
                high: k.high,
                low: k.low,
                close: k.close,
            }));

            klineSeries.setData(klineData);

            // 加载历史数据后，发起实时订阅
            subscribeKlines(symbol, interval);

            // 更新标题
            const now = new Date();
            const lastKline = klineData[klineData.length - 1];
            if (lastKline) {
                addLog('info', `K 线图表已更新：${symbol} ${interval}`);
            }
        } else {
            addLog('warning', `暂无 K 线数据：${symbol} ${interval}`);
        }
    } catch (error) {
        addLog('error', `加载 K 线失败：${error.message}`);
    }
}
```

- [ ] **Step 2: 提交**

```bash
git add web/templates/index.html
git commit -m "feat: loadKlineChart 加载历史数据后发起实时订阅"
```

---

### Task 9: 前端修改周期切换逻辑

**Files:**
- Modify: `web/templates/index.html:2391-2417` (initKlineTimeframeButtons 函数)

- [ ] **Step 1: 确认周期切换时调用 loadKlineChart**

读取 `initKlineTimeframeButtons` 函数，确认点击事件处理中包含：

```javascript
button.addEventListener('click', function() {
    // 移除所有激活状态
    buttons.forEach(btn => {
        btn.classList.remove('active', 'text-primary', 'border-primary');
        btn.classList.add('text-gray-400', 'border-gray-600');
    });

    // 激活当前按钮
    this.classList.remove('text-gray-400', 'border-gray-600');
    this.classList.add('active', 'text-primary', 'border-primary');

    // 更新当前周期并加载数据
    currentKlineInterval = this.getAttribute('data-interval');
    loadKlineChart();  // 这会重新加载数据并更新订阅
});
```

- [ ] **Step 2: 提交（如果无需修改则跳过）**

```bash
# 如果代码已经正确，无需提交
git status
```

---

### Task 10: 前端添加页面卸载时清理订阅

**Files:**
- Modify: `web/templates/index.html:2359-2365` (在 DOMContentLoaded 事件之后)

- [ ] **Step 1: 添加 beforeunload 事件处理器**

在 `DOMContentLoaded` 事件处理器的最后添加：

```javascript
// 页面卸载时清理订阅
window.addEventListener('beforeunload', () => {
    if (currentKlineSubscription) {
        console.log('[DEBUG] 页面卸载，取消 K 线订阅');
        socket.emit('unsubscribe_klines', currentKlineSubscription);
    }
});
```

- [ ] **Step 2: 提交**

```bash
git add web/templates/index.html
git commit -m "feat: 页面卸载时取消 K 线订阅"
```

---

### Task 11: 测试 K 线订阅功能

**Files:**
- Test: 手动测试

- [ ] **Step 1: 启动 Web 服务器**

```bash
cd web
python app.py
```

预期输出：
```
Web 服务器启动：http://0.0.0.0:5001
```

- [ ] **Step 2: 打开浏览器访问 http://localhost:5001**

- [ ] **Step 3: 打开浏览器开发者工具（F12），查看 Console 标签**

- [ ] **Step 4: 等待 WebSocket 连接**

预期看到日志：
```
[DEBUG] Socket.IO connected
[DEBUG] 订阅 K 线：BTC/USDT 4h
[DEBUG] K 线已订阅：BTC/USDT 4h
```

- [ ] **Step 5: 观察 K 线图表更新**

预期：
- 历史数据加载成功
- Console 中持续收到 `[DEBUG] 收到 K 线更新` 日志
- K 线图表实时更新（未闭合 K 线跳动）

- [ ] **Step 6: 切换交易对**

选择其他交易对，预期：
- 先取消旧订阅
- 加载新交易对历史数据
- 订阅新交易对 K 线

- [ ] **Step 7: 切换周期**

点击不同周期按钮（1h, 4h, 1D），预期：
- 先取消旧订阅
- 加载新周期历史数据
- 订阅新周期 K 线

- [ ] **Step 8: 关闭页面**

预期看到日志：
```
[DEBUG] 页面卸载，取消 K 线订阅
```

---

### Task 12: 代码审查和清理

**Files:**
- All modified files

- [ ] **Step 1: 检查是否有未使用的调试日志**

保留 `console.log('[DEBUG] ...)` 日志，便于问题排查

- [ ] **Step 2: 运行语法检查**

```bash
python -m py_compile web/app.py
```

- [ ] **Step 3: 提交最终代码**

```bash
git add -A
git commit -m "chore: 代码审查和清理"
```

---

## 测试检查清单

完成后，验证以下场景：

- [ ] 页面加载后自动订阅 K 线
- [ ] 历史数据加载正确（200 根 K 线）
- [ ] 实时 K 线更新（未闭合 K 线跳动）
- [ ] 切换交易对时更新订阅
- [ ] 切换周期时更新订阅
- [ ] 关闭页面时取消订阅
- [ ] WebSocket 断开重连后自动重新订阅

---

## 回滚方案

如果功能有问题，可以通过以下命令回滚：

```bash
git log --oneline -5
git revert <commit-hash>  # 回滚特定提交
```
