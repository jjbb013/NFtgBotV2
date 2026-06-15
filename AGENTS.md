# AGENTS.md —— tgBot Lite

> 本文档面向不了解本项目的 AI 编码助手。所有内容基于当前 `main` 分支重构后的代码。

## 一、项目概述

- **项目名称**：Telegram 信号交易机器人（tgBot Lite）
- **编程语言**：Python 3.11
- **主程序**：`main.py`（启动 uvicorn + Telegram 后台任务）
- **运行方式**：Docker / 本地直接运行
- **目标平台**：OKX 永续合约（U 本位）

### 主要功能

1. 监听 Telegram 频道交易信号。
2. 解析做多/做空/平仓信号。
3. 为每个 OKX 账户按保证金比例下单，附带止盈止损。
4. 识别平仓信号并执行双向/单向平仓。
5. 定时回扫最近消息补单。
6. 轻量 Dashboard：状态、实时订单、日志、Telegram 网页登录。

## 二、技术栈

| 组件 | 说明 |
|------|------|
| Python 3.11 | 运行语言 |
| Telethon | Telegram 客户端 |
| python-okx | OKX API SDK |
| FastAPI + Jinja2 + uvicorn | Dashboard |
| pymongo | MongoDB 持久化 |
| requests / pytz / python-dotenv | 辅助 |

## 三、项目结构

```text
.
├── main.py                 # 入口
├── config.py               # 环境变量
├── db.py                   # MongoDB 持久化
├── telegram_client.py      # Telegram 客户端
├── core/
│   ├── helpers.py          # 通用工具
│   ├── account.py          # OKXAccount
│   ├── signals.py          # 信号解析
│   └── processor.py        # 信号处理
├── web/
│   ├── app.py              # FastAPI
│   └── templates/          # HTML 模板
├── static/                 # CSS
├── tests/                  # 单元测试
├── Dockerfile
├── requirements.txt
└── README.md
```

## 四、代码约定

1. **模块化**：一个文件一个职责。
2. **环境变量**：所有敏感/可变参数走环境变量，禁止硬编码。
3. **异常处理**：关键操作 try/except，错误写入日志和 Bark/Telegram。
4. **日志**：使用标准 logging + 内存环形缓冲区（`processor.log_buffer`），输出到 stdout。
5. **注释**：核心函数使用中文注释。
6. **测试**：新增功能应补充 `tests/` 下的单元测试。

## 五、构建与运行

```bash
pip install -r requirements.txt
python main.py
```

Docker:

```bash
docker build -t tgbot-lite .
docker run -p 8000:8000 --env-file .env tgbot-lite
```

## 六、环境变量

必需：`TG_API_ID`、`TG_API_HASH`、`TG_CHANNEL_IDS`、`MONGODB_URI`、`DASHBOARD_PASSWORD`。

可选：`TG_LOG_GROUP_ID`、`DASHBOARD_USERNAME`、`DASHBOARD_PORT`、`BARK_KEY`、运行控制变量、OKX 账户变量。

详见 `README.md`。

## 七、Northflank 部署要点

1. 创建 MongoDB addon，将连接字符串注入 `MONGODB_URI`。
2. 暴露 HTTP 端口 `8000`。
3. 健康检查路径 `/health`（无需认证）。
4. 不需要持久卷。
5. 首次部署后访问 `/login` 完成 Telegram 登录。

## 八、测试

```bash
python -m pytest tests/ -v
```

## 九、安全注意事项

1. API Key/Secret/Passphrase、Telegram API、Bark Key 均通过环境变量注入，禁止写入代码。
2. `DASHBOARD_PASSWORD` 必须设置为强密码。
3. 实盘交易前务必在模拟盘（`OKX*_FLAG=1`）测试。
4. MongoDB 连接字符串属于敏感信息，通过 Northflank Secrets 管理。
