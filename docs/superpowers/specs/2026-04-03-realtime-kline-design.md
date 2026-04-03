# 实时 K 线推送系统设计

## 概述

实现 K 线图表的实时数据推送功能，采用混合模式：历史数据从 API 加载，增量数据通过 WebSocket 实时推送。

## 需求

### 功能需求

1. **历史数据加载** - 前端通过 REST API 获取 200 根历史 K 线数据
2. **实时数据推送** - 后端通过交易所 WebSocket 接收 K 线更新，推送到前端
3. **订阅管理** - 页面加载时自动订阅，切换交易对/周期时自动更新订阅
4. **状态区分** - 区分未闭合/已闭合 K 线，前端用不同样式显示

### 非功能需求

1. **低延迟** - K 线数据从交易所到前端的延迟 < 500ms
2. **推送范围** - 仅推送当前图表选中的交易对和周期，避免资源浪费
3. **连接管理** - 支持订阅/取消订阅，避免重复订阅

## 架构设计

### 数据流

```
┌─────────────────┐     WebSocket      ┌─────────────────┐
│   交易所         │ ─────────────────> │ 后端            │
│   Binance/OKX   │    K 线数据        │  (binance.py)   │
└─────────────────┘                     └────────┬────────┘
                                                  │
                                                  │ 回调
                                                  ▼
                                         ┌─────────────────┐
                                         │ DataCollector   │
                                         │ Strategy        │
                                         └────────┬────────┘
                                                  │
                                                  │ SocketIO
                                                  ▼
┌─────────────────┐     WebSocket      ┌─────────────────┐
│   前端           │ <───────────────── │  web/app.py     │
│   index.html    │    kline_update    │  (SocketIO)     │
└─────────────────┘                     └─────────────────┘
         │
         │ HTTP GET
         ▼
┌─────────────────┐
│  /api/klines    │
│  (历史数据)      │
└─────────────────┘
```

### 组件设计

#### 1. 交易所 K 线订阅 (src/exchanges/binance.py, okx.py)

已存在功能：
- `subscribe_klines(symbol, interval, callback)` - 订阅 K 线
- `unsubscribe_klines(symbol, interval)` - 取消订阅
- K 线回调接收 `KLine` 对象，包含 `is_closed` 字段

#### 2. WebSocket 推送 (web/app.py)

新增组件：
- `_kline_push_task` - K 线推送任务
- `_active_kline_subscriptions` - 活跃订阅记录
- `@socketio.on("subscribe_klines")` - 订阅处理器
- `@socketio.on("unsubscribe_klines")` - 取消订阅处理器

#### 3. 前端处理 (web/templates/index.html)

新增功能：
- `subscribeKlines(symbol, interval)` - 发起订阅
- `unsubscribeKlines()` - 取消订阅
- `socket.on('kline_update')` - 接收 K 线更新
- K 线图表增量更新逻辑

## 接口设计

### WebSocket 事件

#### 订阅 K 线

**前端 → 后端:**
```javascript
socket.emit('subscribe_klines', {
    exchange: 'binance',
    symbol: 'BTC/USDT',
    interval: '4h'
});
```

**后端响应:**
```javascript
socket.emit('kline_subscribed', {
    exchange: 'binance',
    symbol: 'BTC/USDT',
    interval: '4h'
});
```

#### K 线数据推送

**后端 → 前端:**
```javascript
socket.emit('kline_update', {
    exchange: 'binance',
    symbol: 'BTC/USDT',
    interval: '4h',
    time: 1712131200000,      // 毫秒时间戳
    open: 65000.0,
    high: 65500.0,
    low: 64800.0,
    close: 65200.0,
    volume: 1234.56,
    is_closed: false          // false=未闭合，true=已闭合
});
```

#### 取消订阅 K 线

**前端 → 后端:**
```javascript
socket.emit('unsubscribe_klines', {
    exchange: 'binance',
    symbol: 'BTC/USDT',
    interval: '4h'
});
```

### REST API

现有 `/api/klines` 接口保持不变：
```
GET /api/klines?symbol=BTC/USDT&interval=4h&limit=200
```

## 前端实现

### K 线订阅管理

```javascript
let currentKlineSubscription = null;

function subscribeKlines(symbol, interval) {
    // 先取消旧订阅
    if (currentKlineSubscription) {
        socket.emit('unsubscribe_klines', currentKlineSubscription);
    }
    
    // 创建新订阅
    currentKlineSubscription = {
        exchange: 'binance',  // 从 UI 获取
        symbol: symbol,
        interval: interval
    };
    
    socket.emit('subscribe_klines', currentKlineSubscription);
}

socket.on('kline_subscribed', (data) => {
    addLog('info', `K 线已订阅：${data.symbol} ${data.interval}`);
});

socket.on('kline_update', (data) => {
    updateKlineChart(data);
});
```

### K 线图表增量更新

```javascript
function updateKlineChart(kline) {
    if (!klineSeries) return;
    
    const candleData = {
        time: kline.time / 1000,  // 转换为秒
        open: kline.open,
        high: kline.high,
        low: kline.low,
        close: kline.close,
    };
    
    // Lightweight Charts 自动处理增量更新
    klineSeries.update(candleData);
    
    // 未闭合 K 线标记（用于样式）
    if (!kline.is_closed) {
        // 可以选择添加视觉标记
    }
}
```

### 未闭合 K 线样式

```javascript
klineSeries = klineChart.addCandlestickSeries({
    upColor: '#26a69a',           // 阳线颜色
    downColor: '#ef5350',         // 阴线颜色
    borderVisible: true,
    wickVisible: true,
});

// 未闭合 K 线通过 alpha 通道实现半透明效果
// 在 updateKlineChart 中根据 is_closed 设置不同颜色
```

## 后端实现

### WebSocket 订阅处理器

```python
_active_kline_subscriptions: Dict[str, Dict] = {}

@socketio.on("subscribe_klines")
def handle_subscribe_klines(data):
    exchange_name = data.get("exchange", "binance")
    symbol = data.get("symbol")
    interval = data.get("interval")
    
    if not symbol or not interval:
        emit("error", {"message": "参数错误"})
        return
    
    # 检查引擎和交易所
    if engine is None or exchange_name not in engine.exchanges:
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
        await _unsubscribe_kline(sub_key)
    
    # 创建回调
    async def kline_callback(kline):
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
    
    # 订阅
    await exch.subscribe_klines(symbol, interval, kline_callback)
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

@socketio.on("unsubscribe_klines")
def handle_unsubscribe_klines(data):
    exchange_name = data.get("exchange", "binance")
    symbol = data.get("symbol")
    interval = data.get("interval")
    
    sub_key = f"{exchange_name}:{symbol}:{interval}"
    await _unsubscribe_kline(sub_key)
```

### 取消订阅逻辑

```python
async def _unsubscribe_kline(sub_key: str):
    if sub_key not in _active_kline_subscriptions:
        return
    
    sub = _active_kline_subscriptions[sub_key]
    exchange_name = sub["exchange"]
    symbol = sub["symbol"]
    interval = sub["interval"]
    
    if exchange_name in engine.exchanges:
        exch = engine.exchanges[exchange_name]
        await exch.unsubscribe_klines(symbol, interval)
    
    del _active_kline_subscriptions[sub_key]
    logger.info(f"K 线已取消订阅：{sub_key}")
```

## 集成点

### 1. loadKlineChart 修改

在 `loadKlineChart()` 函数中：
1. 通过 API 加载历史 K 线数据
2. 调用 `klineSeries.setData()` 设置历史数据
3. 调用 `subscribeKlines()` 发起实时订阅

### 2. initKlineTimeframeButtons 修改

在周期切换时：
1. 更新 `currentKlineInterval`
2. 调用 `loadKlineChart()` 重新加载数据（会自动更新订阅）

### 3. 页面卸载清理

在页面关闭/刷新前：
```javascript
window.addEventListener('beforeunload', () => {
    if (currentKlineSubscription) {
        socket.emit('unsubscribe_klines', currentKlineSubscription);
    }
});
```

## 错误处理

### 1. 交易所断开重连

- 交易所 WebSocket 断开时，自动重连并重新订阅
- Binance/OKX 已有重连逻辑 (`_reconnect_ws`)
- 重连后自动恢复订阅

### 2. SocketIO 断开

- SocketIO 断开时，后端不清除订阅
- SocketIO 重连后，前端重新发起订阅

### 3. 订阅失败处理

- 订阅失败时发送 `error` 事件到前端
- 前端显示错误日志，不阻塞 UI

## 测试计划

### 单元测试

1. 测试 `subscribe_klines` 处理器
2. 测试 `unsubscribe_klines` 处理器
3. 测试 K 线回调函数

### 集成测试

1. 测试完整数据流：交易所 → 后端 → 前端
2. 测试订阅/取消订阅流程
3. 测试交易所重连后订阅恢复

### 手动测试

1. 打开页面，验证 K 线图表加载历史数据
2. 观察 K 线实时更新（未闭合 K 线跳动）
3. 切换交易对，验证新数据推送
4. 切换周期，验证新周期数据推送
5. 关闭页面，验证订阅取消

## 依赖

- 现有 Binance/OKX WebSocket K 线订阅功能
- 现有 Flask SocketIO 基础设施
- Lightweight Charts 图表库

## 风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 交易所 WebSocket 频率限制 | 高 | 限制订阅数量，仅订阅当前选中的交易对/周期 |
| SocketIO 连接断开 | 中 | 前端自动重连，重新订阅 |
| K 线数据延迟 | 低 | 监控延迟，优化推送路径 |
| 前端图表性能 | 低 | 限制更新频率，使用 Lightweight Charts 高效更新 |

## 上线检查清单

- [ ] 后端添加 `subscribe_klines` WebSocket 处理器
- [ ] 后端添加 `unsubscribe_klines` WebSocket 处理器
- [ ] 后端添加 K 线回调和推送逻辑
- [ ] 前端添加 `subscribeKlines` 函数
- [ ] 前端添加 `kline_update` 事件处理器
- [ ] 前端修改 `loadKlineChart` 调用订阅
- [ ] 前端修改周期切换逻辑
- [ ] 测试历史数据加载
- [ ] 测试实时 K 线推送
- [ ] 测试订阅/取消订阅流程
- [ ] 测试交易所重连后订阅恢复
