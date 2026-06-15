# Telegram 信号交易机器人（tgBot Lite）

轻量化的 Telegram 信号交易机器人，监听指定频道交易信号并自动在 OKX 执行开仓/平仓。本项目针对 Northflank PaaS 优化，使用 MongoDB addon 持久化 Telegram session 和已处理消息 ID，无需 Volume。

## 主要特性

- **模块化**：配置、数据库、OKX 账户、信号解析、Telegram 客户端、Web Dashboard 分离。
- **MongoDB 持久化**：使用 `StringSession` 存储 Telegram session；使用 MongoDB 存储已处理消息 ID。
- **轻量 Dashboard**：基于 FastAPI + Jinja2，支持状态查看、实时订单查询、最近日志、Telegram 网页登录向导。
- **Northflank 适配**：单进程启动、日志输出到 stdout、`/health` 探针无需认证。

## 项目结构

```text
.
├── main.py                 # 入口：启动 uvicorn
├── config.py               # 环境变量读取与校验
├── db.py                   # MongoDB 持久化
├── telegram_client.py      # Telegram 客户端、登录向导
├── core/
│   ├── helpers.py          # 工具函数（时间、订单 ID、Bark）
│   ├── account.py          # OKXAccount 封装
│   ├── signals.py          # 信号解析
│   └── processor.py        # 开仓/平仓处理、内存日志缓冲
├── web/
│   ├── app.py              # FastAPI Dashboard
│   └── templates/          # Jinja2 模板
├── static/                 # CSS
├── tests/                  # 单元测试
├── Dockerfile
└── requirements.txt
```

## 环境变量

### 必需

| 变量 | 说明 |
|------|------|
| `TG_API_ID` | Telegram API ID |
| `TG_API_HASH` | Telegram API Hash |
| `TG_CHANNEL_IDS` | 监听频道 ID，多个用逗号分隔 |
| `MONGODB_URI` | MongoDB 连接字符串 |
| `DASHBOARD_PASSWORD` | Dashboard HTTP Basic Auth 密码 |

### 可选

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `TG_LOG_GROUP_ID` | - | Telegram 日志群组 ID |
| `DASHBOARD_USERNAME` | `admin` | Dashboard 用户名 |
| `DASHBOARD_PORT` | `8000` | Dashboard 端口 |
| `BARK_KEY` | - | Bark 推送 key |
| `PATCH_MISSING_SIGNALS_INTERVAL` | `30` | 补单检查间隔（秒） |
| `HEALTH_CHECK_INTERVAL` | `300` | 健康检查间隔（秒） |
| `LOG_BUFFER_SIZE` | `500` | 内存日志缓冲条数 |

### OKX 账户

支持最多 5 个账户：`OKX1_*` ~ `OKX5_*`。

| 变量 | 说明 |
|------|------|
| `OKX1_API_KEY` | API Key |
| `OKX1_SECRET_KEY` | Secret Key |
| `OKX1_PASSPHRASE` | Passphrase |
| `OKX1_FLAG` | `0` 实盘，`1` 模拟盘 |
| `OKX1_LEVERAGE` | 杠杆倍数 |
| `OKX1_POSITION_RATIO` | 开仓保证金占可用余额比例 |
| `OKX1_TP_RATIO` | 止盈比例 |
| `OKX1_SL_RATIO` | 止损比例 |
| `OKX1_ACCOUNT_NAME` | 自定义账户名（可选） |

## 本地开发

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 配置 .env
python main.py
```

首次启动时 Telegram 未登录，访问 `http://localhost:8000/login` 完成登录。

## 测试

```bash
python -m pytest tests/ -v
```

## Northflank 部署

1. 创建 MongoDB addon，将其连接字符串设置为环境变量 `MONGODB_URI`。
2. 配置所有必需环境变量。
3. 暴露 HTTP 端口 `8000`。
4. 健康检查路径使用 `/health`（无需认证）。
5. 部署完成后访问 `/login` 完成 Telegram 登录。

> 不再需要 `DATA_DIR` 或持久卷。
