# Crypto Quant Trader

加密货币量化交易系统，支持多交易所接入、策略回测与实盘交易。

## 功能特性

- **多交易所支持**：Binance、OKX（通过 ccxt 统一接口）
- **策略框架**：内置策略基类，支持自定义策略
- **风控模块**：止损、仓位控制、异常处理
- **Web 界面**：Flask + Vue，实时监控
- **OpenClaw 集成**：通知推送、定时任务

## 项目结构

```
crypto-quant-trader/
├── src/
│   ├── core/           # 核心引擎
│   ├── exchanges/      # 交易所接口
│   ├── strategies/     # 交易策略
│   ├── risk/           # 风控模块
│   ├── data/           # 数据管理
│   └── utils/          # 工具函数
├── tests/              # 测试用例
├── config/             # 配置文件
├── data/               # 本地数据存储
├── docs/               # 文档
├── scripts/            # 运维脚本
├── web/                # Web 界面
├── requirements.txt
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
cd D:\Work\crypto-quant-trader
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置 API Key

复制配置模板并填写：

```bash
copy config\settings.yaml.example config\settings.yaml
```

编辑 `config/settings.yaml`，填入你的 API Key。

### 3. 运行测试（模拟盘）

```bash
python scripts\run_testnet.py
```

### 4. 启动 Web 界面

```bash
python web\app.py
```

访问 http://localhost:5000

## 交易所配置

### Binance

1. 登录 Binance 账户
2. 进入 API Management 创建 API Key
3. 权限设置：Enable Reading + Enable Spot & Margin Trading
4. 将 API Key 和 Secret 填入 `config/settings.yaml`

### OKX

1. 登录 OKX 账户
2. 进入 API 管理创建 API Key
3. 权限设置：读取 + 交易
4. 将 API Key、Secret 和 Passphrase 填入 `config/settings.yaml`

## 风险提示

⚠️ **量化交易存在风险，请谨慎使用！**

- 市场风险：极端行情可能导致重大亏损
- 技术风险：API 故障、网络延迟、策略 Bug
- 监管风险：政策变化可能影响交易

**建议：先在模拟盘充分测试，再考虑实盘。**

## 开发计划

- [x] Phase 1: 基础框架
- [ ] Phase 2: 交易所接口
- [ ] Phase 3: 策略框架
- [ ] Phase 4: 风控模块
- [x] Phase 5: OpenClaw 集成
- [ ] Phase 6: Web 界面

## License

MIT
