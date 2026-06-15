# tgBotV5 Web Dashboard 设计文档

## 1. 背景与目标

### 1.1 背景

当前项目主程序为 `tgBotV4.py`，部署在 Northflank 上，通过 Telethon 监听 Telegram 频道交易信号并自动在 OKX 执行下单/平仓。

每次 Telegram session 失效或需要重新登录时，用户必须进入 Northflank 终端运行脚本、接收验证码、输入密码，操作繁琐且无法直接看到当前登录/监听状态。

### 1.2 目标

新增 `tgBotV5.py`，将 Telegram 监听逻辑与 Web Dashboard 合并为单一进程，提供网页版管理界面，实现：

1. 查看 Telegram 登录状态、session 有效性、监听频道列表。
2. 查看当前运行的程序版本（tgBotV4/V5）与 git commit 信息。
3. 查看每个 OKX 账户的连接状态、USDT 余额、最近 7 天历史盈亏、最近 20 条历史订单。
4. 在网页上直接完成 Telegram 重新登录，并自动恢复监听。
5. 在网页上查看最近 100 条运行日志，无需登录 Northflank 后台。
6. 不影响原有 `tgBotV4.py` 功能，保留快速回滚能力。

## 2. 总体架构

```
┌─────────────────┐     ┌──────────────────────────────┐
│   Northflank    │────▶│         tgBotV5.py           │  :8000
│   Public Port   │     │  ┌────────────────────────┐  │
└─────────────────┘     │  │  Telegram 监听循环      │  │
                        │  │  (events.NewMessage)   │  │
                        │  ├────────────────────────┤  │
                        │  │  后台任务               │  │
                        │  │  (补单/健康检查)        │  │
                        │  ├────────────────────────┤  │
                        │  │  FastAPI Web Dashboard │  │
                        │  └────────────────────────┘  │
                        └──────────────────────────────┘
                                    │
                        ┌───────────┴───────────┐
                        ▼                       ▼
              data/sessions/*.session      data/processed_message_ids.json
```

### 2.1 关键设计决策

- **单进程合并**：`tgBotV5.py` 同时运行 Telegram 监听和 FastAPI Web 服务，共享同一个 asyncio 事件循环。这样 Web Dashboard 可以直接访问 `client.is_connected()` 等内部状态，且重新登录时无需停止其他进程。
- **保留 `tgBotV4.py`**：作为稳定 fallback，出问题可快速回滚。
- **单 worker Uvicorn**：适配 Northflank 0.2 vCPU / 512 MB 低配环境。
- **OKX 调用线程池**：避免同步 OKX SDK 调用阻塞主事件循环。

## 3. 文件与模块划分

### 3.1 新增/修改文件

| 文件 | 用途 | 操作 |
|------|------|------|
| `tgBotV5.py` | 合并 Telegram 监听 + FastAPI Web Dashboard | 新增 |
| `templates/dashboard.html` | Jinja2 页面模板 | 新增 |
| `static/dashboard.css` | 页面样式 | 新增 |
| `static/dashboard.js` | 前端交互逻辑（登录向导、AJAX 刷新） | 新增 |
| `supervisord.conf` | 改为运行 `tgBotV5.py` | 修改 |
| `README.md` | 补充 V5 部署说明 | 修改 |
| `AGENTS.md` | 补充 V5 架构说明 | 修改 |
| `project_log.md` | 记录变更日志 | 修改 |

### 3.2 保留不变文件

- `tgBotV4.py`：原有监听逻辑不变，作为 fallback。
- `utils.py`：`tgBotV5.py` 复用现有工具函数。
- `requirements.txt`：已有 `fastapi` / `uvicorn` / `python-multipart`，无需新增依赖。

### 3.3 `tgBotV5.py` 内部模块

| 模块 | 职责 |
|------|------|
| `config` | 读取环境变量 |
| `telegram_client` | Telegram client 创建、监听、重新登录 |
| `signal_handlers` | 信号解析、下单、平仓（从 tgBotV4 复用） |
| `background_tasks` | 补单、健康检查 |
| `web_app` | FastAPI 应用、路由、认证 |
| `okx_api` | OKX 余额、账单、历史订单查询（线程池包装） |
| `log_buffer` | 内存日志缓存，供 Web 展示 |
| `main` | 启动入口，协调 Telegram 和 FastAPI 运行 |

## 4. 页面布局与功能

Web Dashboard 为单页应用，分为以下区块：

### 4.1 顶部标题栏

- 项目名称
- 当前时间（上海时区）
- 登出按钮

### 4.2 系统状态概览

- 当前运行版本：`tgBotV5`
- Git commit hash、提交信息、提交时间
- `tgBotV5` 进程状态：运行中
- 全局手动刷新按钮

### 4.3 Telegram 状态卡片

- Session 文件路径
- 登录状态：有效 / 失效 / 未知
- 当前用户名称/ID
- 监听频道列表（从 `TG_CHANNEL_IDS` 解析）
- 最后一次消息监听时间
- 如果失效：显示"重新登录"按钮

### 4.4 Telegram 登录向导

点击"重新登录"后展开多步表单：

1. 输入手机号
2. 输入验证码
3. 输入二步验证密码（如需要）
4. 显示登录结果，自动恢复监听

### 4.5 OKX 账户概览

每个 OKX 账户一张卡片：

- 账户名称（如 `OKX1` / `OKX2`）
- 连接状态：正常 / 异常
- USDT 可用余额
- 最近 7 天已实现盈亏汇总
- "查看最近 20 条订单"按钮（展开表格）

### 4.6 OKX 历史订单表格

- 交易对
- 方向（开多/开空/平多/平空）
- 数量
- 价格
- 状态
- 时间

默认显示最近 20 条，按时间倒序。

### 4.7 运行日志查看

- 显示最近 100 条合并后的 stdout/stderr 日志
- 独立刷新按钮
- 自动隐藏敏感信息
- 按时间倒序排列

## 5. 认证与 Telegram 登录流程

### 5.1 认证

- 使用 HTTP Basic Auth
- 用户名/密码通过环境变量配置：
  - `DASHBOARD_USERNAME`
  - `DASHBOARD_PASSWORD`
- 未配置时服务拒绝启动

### 5.2 Telegram 重新登录流程

```text
用户点击"重新登录"
        │
        ▼
[前端] POST /api/telegram/login/start
       { phone: "+8612345678901" }
        │
        ▼
[后端] 1. 暂停后台任务（补单/健康检查）
       2. 断开当前 Telegram client
       3. 创建临时新 client，调用 send_code_request(phone)
       4. 返回 { phone_code_hash }
        │
        ▼
[前端] 输入验证码，POST /api/telegram/login/verify
       { phone, code, phone_code_hash }
        │
        ▼
[后端] 1. 调用 sign_in(phone, code, phone_code_hash)
       2. 如果需要 2FA，返回 { need_password: true }
        │
        ▼
[前端] 输入二步验证密码，POST /api/telegram/login/password
       { password }
        │
        ▼
[后端] 1. 调用 check_password(password)
       2. 保存 session 文件
       3. 更新 data/last_session_path.txt
       4. 替换全局 client
       5. 重新注册事件处理器
       6. 恢复后台任务
       7. 返回 { success: true }
```

### 5.3 异常处理

- 任何步骤失败都会尝试恢复原有 client 或保持服务可访问。
- 确保不会重复注册事件监听器。

## 6. OKX 数据展示

### 6.1 数据范围

- **余额**：实时查询 USDT 可用余额。
- **历史盈亏**：基于 OKX 账单流水（`/api/v5/account/bills`），汇总最近 7 天的已实现盈亏。
- **历史订单**：调用 OKX 历史订单接口，默认返回最近 20 条。

### 6.2 性能优化

- 所有 OKX SDK 同步调用通过 `asyncio.to_thread` 或 `run_in_executor` 放入线程池执行。
- 数据为手动刷新，不自动轮询，降低 API 调用频率。

## 7. 日志展示

### 7.1 实现方式

- `tgBotV5.py` 使用自定义日志 Handler，将日志同时写入文件和内存队列（最大保存 1000 条）。
- Web 页面通过 API 读取内存队列中的最近 100 条。
- 返回前进行敏感信息过滤。

### 7.2 敏感信息过滤

自动隐藏以下信息：

- 手机号
- Telegram 验证码
- Telegram 二步验证密码
- OKX API Key
- OKX Secret Key
- OKX Passphrase
- Bark Key
- Telegram API Hash

使用正则表达式替换为 `***`。

## 8. 部署与 Supervisor 配置

### 8.1 `supervisord.conf`

```ini
[supervisord]
nodaemon=true

[program:tgBotV5]
command=python ./tgBotV5.py
directory=/app
autostart=true
autorestart=true
stdout_logfile=/app/logs/tgBotV5.out.log
stderr_logfile=/app/logs/tgBotV5.err.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
stderr_logfile_maxbytes=50MB
stderr_logfile_backups=10
```

### 8.2 新增环境变量

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `DASHBOARD_USERNAME` | 是 | - | Web 登录用户名 |
| `DASHBOARD_PASSWORD` | 是 | - | Web 登录密码 |
| `DASHBOARD_PORT` | 否 | `8000` | Web 服务端口 |

### 8.3 部署步骤

1. 本地测试：`python tgBotV5.py`
2. 构建镜像：`docker build -t tg-signal-bot:v5 .`
3. Northflank 添加环境变量 `DASHBOARD_USERNAME` / `DASHBOARD_PASSWORD`
4. Northflank 暴露 `8000` 端口为公开 URL
5. 重新部署，访问 Northflank 提供的 URL

### 8.4 版本控制

- 所有 `tgBotV5` 相关代码改动在独立分支（如 `feat/tgBotV5-dashboard`）上进行，不直接提交到 `main` 分支。
- 本地开发时可以使用 git worktree 或独立 clone 保持隔离。
- 完成后通过 Pull Request / Merge Request 合并到 `main`。

## 8.5 回滚方案

如果 `tgBotV5` 运行异常，将 `supervisord.conf` 中的 `command` 改回 `python ./tgBotV4.py`，重新部署即可。

## 9. 安全考虑

1. **认证保护**：强制 HTTP Basic Auth，无认证信息时拒绝启动。
2. **Session 文件权限**：新 session 文件设置为 `600`。
3. **敏感信息不泄露**：页面不展示 API Key、Secret、Passphrase、验证码、密码。
4. **日志过滤**：Web 日志自动隐藏手机号、验证码、密码、API 凭证等。
5. **资源保护**：单 worker 运行，OKX 调用放入线程池。
6. **回滚能力**：保留 `tgBotV4.py` 作为 fallback。

## 10. 资源与性能

- **运行环境**：Northflank 0.2 vCPU / 512 MB
- **Uvicorn 配置**：`workers=1`，单进程运行
- **内存预估**：Telethon client + FastAPI + 日志缓存约占用 100-200 MB，512 MB 足够。
- **CPU 预估**：Telethon 监听和 OKX 查询均为 IO 密集型，0.2 vCPU 可满足。

## 11. 未来扩展（不在本期实现）

- 实时日志推送（WebSocket / SSE）
- 在网页上手动触发下单/平仓
- 多环境配置切换（开发/生产）
- 操作审计日志（记录谁在网页上执行了重新登录等操作）
