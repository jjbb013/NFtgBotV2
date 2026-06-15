# tgBot Lite 重构设计文档

> 日期：2026-06-16  
> 目标：在 `main` 分支基础上，把 Telegram 信号交易机器人改造成轻量化、模块化、适配 Northflank PaaS 的版本，并保留一个轻量 Dashboard。

---

## 1. 背景与目标

### 1.1 当前问题

- `tgBotV4.py` 单文件接近 550 行，职责混杂（配置、信号解析、下单、Telegram、日志）。
- `requirements.txt` 包含未使用的依赖（`sqlalchemy`、`fastapi`、`uvicorn`、`python-multipart`、`jinja2` 等）。
- 仓库中存在 `tgBotV2.py`、`tgBotV3.py`、`okx_account.py` 等历史/未集成文件。
- 使用本地文件（`DATA_DIR` + Volume）保存 `session` 文件和 `processed_message_ids.json`。
- 通过 `supervisor` 启动，增加一个常驻进程和文件日志，不符合 Northflank 最佳实践。

### 1.2 设计目标

1. **轻量化**：只保留运行所需的依赖；只保留核心文件。
2. **模块化**：按职责拆分为配置、数据库、OKX 账户、信号解析、信号处理、Telegram 客户端、Web Dashboard、入口程序。
3. **适配 Northflank**：
   - 使用 Northflank MongoDB addon 替代 Volume 持久化。
   - Telegram 使用 `StringSession`，把 session 字符串存入 MongoDB。
   - 日志输出到 `stdout`/`stderr`。
   - 提供 `/health` 探针，供 Northflank 判断服务存活。
4. **保留 Dashboard**：提供一个轻量的 FastAPI + Jinja2 网页，可查看状态、实时订单、最近日志、Telegram 网页登录向导。
5. **稳定可执行**：核心交易逻辑保持不变，确保回测/模拟盘可验证。

---

## 2. 架构概览

```text
┌─────────────────────────────────────────────────────────────┐
│                         main.py                              │
│  - 启动 uvicorn（单 worker，port 8000）                       │
│  - 在 uvicorn 事件循环里启动 Telegram 客户端后台任务           │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
   web/app.py              telegram_client.py
   FastAPI Dashboard       Telethon 客户端
        │                         │
        │    ┌────────────────────┘
        │    ▼
        │ core/processor.py
        │  - process_open_signal
        │  - process_close_signal
        │
        ▼
   core/account.py
   OKXAccount（每个账户一个实例）
        │
        ▼
   db.py  ── MongoDB
   (session string / processed IDs)
```

---

## 3. 模块设计

### 3.1 `config.py`

- 加载 `.env`（仅本地开发）。
- 读取并校验环境变量：
  - Telegram：`TG_API_ID`、`TG_API_HASH`、`TG_CHANNEL_IDS`（必填）；`TG_LOG_GROUP_ID`（可选，未配置时只写本地日志）
  - OKX：`OKX1_*` ~ `OKX5_*`
  - Dashboard：`DASHBOARD_USERNAME`、`DASHBOARD_PASSWORD`、`DASHBOARD_PORT`（默认 8000）
  - MongoDB：`MONGODB_URI`
  - 运行控制：`PATCH_MISSING_SIGNALS_INTERVAL`、`HEALTH_CHECK_INTERVAL`、`LOG_BUFFER_SIZE`
- 提供 `get_test_accounts()`，返回账户列表。
- 关键变量缺失时直接退出并打印明确错误。

### 3.2 `db.py`

- 使用 `pymongo` 连接 `MONGODB_URI`。
- 数据库名：`tgbot_lite`。
- 集合：
  - `state`：单文档，存 `session_string` 和 `processed_message_ids`。
- 接口：
  - `load_session_string() -> str | None`
  - `save_session_string(session_string: str) -> None`
  - `load_processed_ids() -> dict[int, set[int]]`
  - `save_processed_ids(ids: dict[int, set[int]]) -> None`
  - 存储时把 `set[int]` 转为 `list[int]`；加载时再转回 `set`。每个 channel 最多保留最近 1000 条 ID。
- 启动时若连接失败，打印错误并退出，避免无持久化运行时下单导致重复信号。

### 3.3 `core/account.py` — `OKXAccount`

- 每个 OKX 账户实例化一个 `OKXAccount`。
- 内部持有 `TradeAPI`、`AccountAPI`、`MarketDataAPI`。
- 方法：
  - `get_price(symbol) -> float | None`
  - `get_balance() -> float | None`
  - `place_order(action, symbol, size) -> dict`
  - `close_positions(symbol, close_type) -> dict`
  - `get_orders(inst_id, limit=10) -> list[dict]`（供 Dashboard 实时查询）
  - `set_leverage(symbol, leverage) -> dict`
- 所有方法内部捕获异常，返回统一结构 `{"success": bool, ...}`。

### 3.4 `core/signals.py`

- `extract_trade_info(message) -> (action, symbol) | (None, None)`
- `extract_close_signal(message) -> (close_type, symbol) | (None, None)`
- 保留原有正则逻辑，仅做代码整理和注释。

### 3.5 `core/processor.py`

- `process_open_signal(action, symbol, msg_text, accounts)`
  - 获取每个账户余额 → 计算保证金 → 获取价格 → 币张转换 → 下单 → 发送日志/Bark。
  - 价格只在处理器开头获取一次，避免每个账户重复调用行情接口。
  - 使用 `asyncio.Lock` 保证同一信号不会被并发处理多次。
- `process_close_signal(close_type, symbol, msg_text, accounts)`
  - 遍历账户平仓，发送日志/Bark。
- 日志发送：
  - 保留 Bark 推送（可选，依赖 `BARK_KEY`）。
  - 保留 Telegram 日志群组关键事件推送，但**不再转发每一条频道原始消息**到日志群。
  - 关键事件定义：启动价格播报、杠杆设置结果、开仓/平仓结果及错误、Telegram/OKX 异常告警。

### 3.6 `telegram_client.py`

- 使用 `Telethon` 的 `StringSession`。
- 启动流程：
  1. 从 MongoDB 读取 `session_string`。
  2. 创建 `TelegramClient(StringSession(session_string), ...)`。
  3. 调用 `await client.start()`。
  4. 如果登录成功且 session_string 为空，调用 `client.session.save()` 并写入 MongoDB。
  5. 注册 `events.NewMessage` 处理器。
  6. 启动 `check_and_patch_missing_signals` 和 `health_check` 后台任务。
  7. 保持 `await client.disconnected` 监听，断线时自动重连（Telethon 默认行为）。
- Web 登录向导接口（供 `web/app.py` 调用）：
  - `start_login(phone) -> phone_code_hash`
  - `confirm_login(phone, code, phone_code_hash) -> session_string`
  - 使用全局状态保存 pending login，加锁保护。

### 3.7 `web/app.py`

- FastAPI app。
- 认证：HTTP Basic Auth（`DASHBOARD_USERNAME` / `DASHBOARD_PASSWORD`）。
- 路由：
  - `GET /health`：未认证，返回 `{"status": "ok", "telegram_connected": bool}`。
  - `GET /`：Dashboard 首页，显示状态、账户、最近日志。
  - `GET /orders`：页面展示各账户最近订单（实时查 OKX）。
  - `GET /api/orders?account_idx=1`：JSON 接口，返回订单列表。
  - `GET /logs`：返回内存日志缓冲 JSON。
  - `GET /login`：Telegram 登录向导页面。
  - `POST /api/login/start`：发送验证码。
  - `POST /api/login/confirm`：确认登录，保存 session_string。
- 模板：使用 Jinja2，文件放在 `templates/`。
- 静态资源：`static/style.css`（极简样式）。

### 3.8 `main.py`

- 入口程序。
- 配置 uvicorn：`host="0.0.0.0"`, `port=8000`, `workers=1`, `loop="asyncio"`。
- 创建 Telegram 客户端后台任务：`asyncio.create_task(telegram_client.start())`。
- 调用 `server.serve()`。
- 优雅退出：使用 FastAPI `lifespan` 管理 Telegram 后台任务；收到 `SIGTERM` 时先停止 uvicorn，再取消后台任务并断开 Telegram 客户端。

---

## 4. 数据流

### 4.1 启动流程

1. `main.py` 启动 uvicorn。
2. uvicorn 启动后，在 `lifespan` 或 `main()` 中启动 Telegram 后台任务。
3. Telegram 任务从 MongoDB 读取 session_string，尝试登录。
4. 登录成功后初始化 `processed_message_ids`。
5. 后台任务启动补单和健康检查。

### 4.2 信号处理流程

1. Telegram 新消息触发 `handler(event)`。
2. 检查 `processed_message_ids`，已处理则跳过。
3. 解析开仓/平仓信号。
4. 调用 `process_open_signal` / `process_close_signal`。
5. 更新 `processed_message_ids` 并保存到 MongoDB。
6. 发送关键日志到 Telegram 日志群和 Bark。

### 4.3 Dashboard 数据流

- 状态页：读取内存状态（启动时间、Telegram 连接状态、账户列表、最近内存日志）。
- 订单页：调用 `OKXAccount.get_orders()` 实时查询 OKX。
- 登录页：通过 API 调用 `telegram_client.start_login` / `confirm_login`。

---

## 5. 依赖调整

### 5.1 `requirements.txt`

移除：

- `sqlalchemy`

保留/新增：

```text
telethon
requests
pytz
python-okx
python-dotenv
pymongo
fastapi
jinja2
uvicorn
python-multipart
```

### 5.2 `Dockerfile`

- 基于 `python:3.11-slim`。
- 不再安装 `supervisor`。
- `CMD ["python", "main.py"]`。
- 暴露 `8000`。
- 不再创建 `/data` 目录（使用 MongoDB 替代）。

### 5.3 启动脚本

- 删除或简化 `start.sh`：仅保留创建目录等一次性操作，或删除由 Dockerfile 直接执行 `python main.py`。
- 删除 `supervisord.conf`。

---

## 6. 文件清理

删除以下文件（确认已回退到 `main` 分支后不再需要）：

- `tgBotV2.py`
- `tgBotV3.py`
- `okx_account.py`
- `supervisord.conf`
- `start.sh`（如 Dockerfile 不再使用）

删除：

- `tgBotV2.py`
- `tgBotV3.py`
- `tgBotV4.py`（交易逻辑已迁移到 `core/` 模块，原文件删除；历史版本可在 git 中找回）
- `okx_account.py`（由新的 `core/account.py` 替代）
- `utils.py`（工具函数迁移到 `core/helpers.py`，原文件删除）
- `supervisord.conf`
- `start.sh`

保留：

- `generate_session.py`、`generate_session_v2.py`、`list_dialogs.py`：作为可选的本地命令行辅助工具保留，但新部署流程以 Dashboard 网页登录为主。
- `README.md`、`project_log.md`、`AGENTS.md`：同步更新以反映新结构。

---

## 7. 部署到 Northflank

### 7.1 Addon

1. 在项目里创建 **MongoDB** addon。
2. 把 addon 的 connection string 注入环境变量 `MONGODB_URI`。

### 7.2 环境变量

除原有 Telegram/OKX 变量外，新增：

- `MONGODB_URI`
- `DASHBOARD_USERNAME`
- `DASHBOARD_PASSWORD`
- `DASHBOARD_PORT=8000`

### 7.3 网络

- 暴露 HTTP 端口 `8000`。
- 健康检查路径：`/health`（无需认证）。
- 不需要持久卷（Volume）。

### 7.4 首次部署

1. 部署成功后，访问 `/login`。
2. 输入手机号，获取验证码。
3. 输入验证码完成 Telegram 登录。
4. session_string 自动写入 MongoDB。
5. 后续重启无需再次登录。

---

## 8. 错误处理与稳定性

- **MongoDB 连接失败**：启动时直接退出，避免无持久化运行导致重复下单。
- **Telegram 登录失败**：Dashboard 仍可访问，`/health` 返回 `telegram_connected=false`，页面提示需要登录。
- **OKX API 异常**：单个账户异常不影响其他账户；错误信息写入内存日志并推送 Bark/Telegram。
- **断线重连**：Telethon 客户端默认自动重连；健康检查每 5 分钟验证 `client.is_connected()`。
- **内存日志上限**：默认 500 条，防止长期运行占用过多内存。
- **processed_message_ids 上限**：每个 channel 最多保留最近 1000 条 ID，超过时 trim，防止文档无限增长。

---

## 9. 测试与验收

1. **本地测试**：
   - 配置 `.env`（含本地/测试 MongoDB URI，或指向 Northflank addon 的 forward 地址）。
   - 启动 `python main.py`。
   - 访问 `http://localhost:8000/login` 完成登录。
   - 访问 `/health`、`/orders`、`/logs` 检查正常。
2. **模拟盘测试**：
   - 设置 `OKX1_FLAG=1`。
   - 向监听频道发送测试信号，观察 Dashboard 和日志。
3. **Northflank 部署**：
   - 创建 MongoDB addon，配置环境变量。
   - 部署分支，确认 `/health` 返回 200。
   - 通过 Dashboard 登录 Telegram 并验证信号处理。

---

## 10. 决策记录

| 决策 | 选项 | 理由 |
|------|------|------|
| Web 形态 | FastAPI 轻量 Dashboard | 满足网页查看需求，资源占用可控 |
| 持久化 | MongoDB addon | 替代 Volume，适配 Northflank PaaS |
| Telegram session | `StringSession` + MongoDB | 无需文件系统持久化 |
| 启动方式 | `main.py` 直接启动 uvicorn | 去掉 supervisor，减少进程和内存 |
| 日志 | 内存环形缓冲区 + stdout | Dashboard 可见最近日志，Northflank 控制台可查看 |
| 旧文件 | 删除 V2/V3/okx_account.py | 减少体积和认知负担 |
| 交易记录 | 实时查 OKX API | 不落地存储，最轻量 |
| 认证 | HTTP Basic Auth | 实现简单，无需引入额外用户系统 |
