# AGENTS.md —— 供 AI Coding Agent 阅读的项目说明

> 本文档面向不了解本项目的 AI 编码助手。所有内容基于当前项目实际文件编写，请勿基于假设推断。

## 一、项目概述

本项目是一个 **Telegram 信号交易机器人**，用于监听指定 Telegram 频道中的交易信号，并自动在 OKX 交易所执行对应的开仓/平仓操作。

- **项目名称**：Telegram 信号交易机器人（仓库目录名 `NFtgBotV2`）
- **编程语言**：Python 3.11
- **当前主程序**：`tgBotV5.py`（`tgBotV4.py` 保留作为 fallback）
- **进程管理**：`supervisord`
- **部署方式**：Docker（也可本地直接运行）
- **目标平台**：OKX 永续合约（U 本位），如 `BTC-USDT-SWAP`、`ETH-USDT-SWAP`、`DOGE-USDT-SWAP`、`SOL-USDT-SWAP`

### 主要功能

1. **频道监听**：通过 Telethon 监听一个或多个 Telegram 频道的新消息。
2. **信号解析**：从文本中提取“做多/做空/平仓”信号及交易对。
3. **自动下单**：为每个配置的 OKX 账户按保证金比例计算下单量，并下市价单，附带止盈止损（One-Cancels-Other / attachAlgoOrds）。
4. **自动平仓**：识别止盈、止损、MA 止损等关键词，平掉对应方向或双向持仓。
5. **补单机制**：定时回扫最近 20 条历史消息，防止漏单。
6. **健康检查**：周期性检查 Telegram 连接状态，异常时主动退出以便 supervisor 重启。
7. **通知推送**：
   - 所有关键日志推送至 Telegram 日志群组（`TG_LOG_GROUP_ID`）。
   - 下单/平仓结果通过 Bark 推送（`BARK_KEY`）。
8. **多账户支持**：最多支持 5 个 OKX 账户，分别独立下单、平仓、设置杠杆。
9. **Web Dashboard**（V5 新增）：通过 FastAPI 提供系统状态、Telegram/OKX 状态、最近日志查看以及 Telegram 网页重新登录功能。

---

## 二、技术栈

| 组件 | 说明 |
|------|------|
| Python 3.11 | 运行语言，Dockerfile 基于 `python:3.11-slim` |
| Telethon | Telegram MTProto 客户端库，用于监听消息和发送日志 |
| python-okx | OKX 官方 Python SDK，调用交易/账户/行情/公共数据接口 |
| requests | 用于 Bark 推送的 HTTP 请求 |
| python-dotenv | 本地开发时自动加载 `.env` 环境变量 |
| pytz | 时区处理（项目实际使用 `datetime.timezone(timedelta(hours=8))` 处理上海时间）|
| Supervisor | 容器内进程守护，通过 `supervisord.conf` 配置 |
| Docker | 容器化部署 |

> 注：`requirements.txt` 中列出的 `fastapi`、`uvicorn`、`jinja2` 已在 `tgBotV5.py` 中使用；`sqlalchemy`、`python-multipart` 目前未被使用。

---

## 三、项目结构

```
.
├── tgBotV5.py              # 当前主程序（V5）：Telegram 监听 + Web Dashboard
├── tgBotV4.py              # V4 版本，保留作为 fallback
├── tgBotV3.py              # V3 版本，新增 DOGE/SOL 及 MA 止损双向平仓
├── tgBotV2.py              # V2 版本，历史稳定版本
├── utils.py                # 公共工具函数：时间、订单参数、杠杆设置、Bark 通知
├── okx_account.py          # OKXAccount 类封装（当前未被主程序导入使用，处于独立状态）
├── generate_session.py     # 手动生成 Telegram session 文件（保留旧 session）
├── generate_session_v2.py  # 生成 session 文件 V2：清空旧 session、可选重启服务
├── list_dialogs.py         # 查看当前账号的频道/群组 ID 列表
├── requirements.txt        # Python 依赖
├── Dockerfile              # Docker 镜像构建
├── start.sh                # 本地/容器启动脚本，创建目录后启动 supervisord
├── supervisord.conf        # Supervisor 配置，默认运行 tgBotV5.py
├── README.md               # 面向人类的部署与配置说明（中文）
├── project_log.md          # 项目日志与规范约定，包含日志格式、部署建议
├── AGENTS.md               # 本文件：面向 AI 编码助手的项目说明
├── templates/
│   └── dashboard.html      # Web Dashboard Jinja2 模板
├── static/
│   ├── dashboard.css       # Dashboard 样式
│   └── dashboard.js        # Dashboard 前端交互
├── data/
│   ├── sessions/           # Telegram session 文件存放目录
│   ├── processed_message_ids.json   # 已处理消息 ID 缓存
│   └── last_session_path.txt        # 记录最近一次使用的 session 路径
└── logs/                   # 运行日志目录（需挂载持久化）
```

---

## 四、代码组织与模块划分

### 1. 主程序（tgBotV5.py）

单文件结构，Telegram 监听与 Web Dashboard 运行在同一个 asyncio 事件循环中，主要按功能分为以下几个区域：

| 区域 | 说明 |
|------|------|
| 初始配置与环境变量 | 加载 `.env`，读取 Telegram/OKX 配置，校验关键变量 |
| Session 管理 | `get_session_file()`：自动复用/选择/新建 Telegram session 文件 |
| 账户与数据 | `get_test_accounts()`：读取 `OKX1_` ~ `OKX5_` 账户配置；已处理消息 ID 缓存读写 |
| 信号解析 | `extract_trade_info()` 解析开仓信号；`extract_close_signal()` 解析平仓信号 |
| OKX 与 Bark 逻辑 | 获取行情、余额、下单、平仓、构建 Bark 通知内容 |
| 信号处理器 | `process_open_signal()`、`process_close_signal()`：遍历账户执行下单/平仓，并推送日志 |
| 后台任务 | `health_check()`、`check_and_patch_missing_signals()` |
| Web Dashboard | FastAPI 应用、HTTP Basic Auth、静态文件保护、Jinja2 模板、系统/Telegram/OKX 状态 API、日志 API、Telegram 重新登录 API |
| 主入口 | `main()`：初始化 Telegram 客户端、登录、初始化已处理 ID、设置杠杆、播报开盘价、启动后台任务、启动 uvicorn 服务 |

### 2. 工具模块（utils.py）

- `get_shanghai_time(fmt)`：返回上海时区时间字符串。
- `generate_clord_id(prefix)`：生成客户订单 ID。
- `build_order_params(...)`：构建 OKX 下单参数，包括附带止盈止损的 `attachAlgoOrds`。
- `send_bark_notification(title, content, group)`：向 Bark 推送通知，group 强制为 `NF-TgBotV2`。
- `set_account_leverage(...)`：设置 OKX 合约杠杆。

### 3. OKXAccount 类（okx_account.py）

封装了单个 OKX 账户的下单、平仓、查价、设杠杆等操作。当前 `tgBotV4.py` 未导入该文件，而是直接调用 OKX API。`okx_account.py` 处于独立可用但未被主程序集成的状态。

---

## 五、构建与运行命令

### 1. 本地开发运行

```bash
# 创建虚拟环境并安装依赖
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 配置环境变量（本地开发建议 .env.local 或 .env）
cp .env.example .env.local
# 编辑 .env.local 填入 TG_API_ID、TG_API_HASH、OKX API 等

# 直接运行主程序
python tgBotV5.py
```

> 主程序会依次尝试加载 `.env.local` 和 `.env`；本地开发时环境文件名应为 `.env` 或 `.env.local`。

### 2. Docker 构建与运行

```bash
# 构建镜像
docker build -t tg-signal-bot .

# 运行容器（推荐挂载 data 与 logs 目录持久化）
docker run -d --name tg-signal-bot \
  -v $PWD/data:/app/data \
  -v $PWD/logs:/app/logs \
  --env-file $PWD/.env \
  -p 8000:8000 \
  tg-signal-bot
```

> Dockerfile 中 `EXPOSE 8000`，`tgBotV5.py` 启动后会在此端口提供 Web Dashboard。

### 3. 通过 start.sh 启动

```bash
chmod +x start.sh
./start.sh
```

脚本会创建 `/data/sessions`、`/data/logs`，然后启动 `supervisord`。

### 4. Supervisor 进程管理

- 配置文件：`supervisord.conf`
- 默认运行：`python ./tgBotV5.py`
- 如需切换版本，修改 `command` 为 `python ./tgBotV4.py`、`python ./tgBotV3.py` 或 `python ./tgBotV2.py`，并同步修改 `program:` 段落名与日志文件名。

---

## 六、环境变量

### 必需变量

| 变量名 | 说明 |
|--------|------|
| `TG_API_ID` | Telegram API ID |
| `TG_API_HASH` | Telegram API Hash |
| `TG_CHANNEL_IDS` | 监听的 Telegram 频道 ID，多个用逗号分隔 |
| `DASHBOARD_USERNAME` | Web Dashboard 登录用户名（V5 必填）|
| `DASHBOARD_PASSWORD` | Web Dashboard 登录密码（V5 必填）|
| `DASHBOARD_PORT` | Web Dashboard 端口，默认 `8000`（V5 可选）|

### 日志与通知变量

| 变量名 | 说明 |
|--------|------|
| `TG_LOG_GROUP_ID` | 用于接收日志的 Telegram 群组/频道 ID |
| `BARK_KEY` | Bark 推送 key，不配置则不发 Bark 通知 |

### OKX 账户变量（以账户 1 为例，最多 5 个账户）

| 变量名 | 说明 |
|--------|------|
| `OKX1_API_KEY` | API Key |
| `OKX1_SECRET_KEY` | Secret Key |
| `OKX1_PASSPHRASE` | Passphrase |
| `OKX1_FLAG` | `0` 实盘，`1` 模拟盘 |
| `OKX1_LEVERAGE` | 杠杆倍数 |
| `OKX1_POSITION_RATIO` | 开仓保证金占总可用余额比例（如 `0.25`）|
| `OKX1_TP_RATIO` | 止盈比例，默认 `0.01` |
| `OKX1_SL_RATIO` | 止损比例，默认 `0.027` |
| `OKX1_ACCOUNT_NAME` | 自定义账户名（V4 新增，默认 `OKX1`）|

### 旧版固定数量变量（V2/V3 使用）

| 变量名 | 说明 |
|--------|------|
| `OKX1_FIXED_QTY_BTC` | BTC 固定下单数量 |
| `OKX1_FIXED_QTY_ETH` | ETH 固定下单数量 |
| `OKX1_FIXED_QTY_DOGE` | DOGE 固定下单数量（V3 新增）|
| `OKX1_FIXED_QTY_SOL` | SOL 固定下单数量（V3 新增）|

### 运行控制变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DATA_DIR` | `./data` | 数据持久化根目录，Northflank 部署建议 `/data` |
| `SESSION_DIR` | `./data/sessions` | session 文件目录 |
| `PATCH_MISSING_SIGNALS_INTERVAL` | `30` | 历史消息补单检查间隔（秒）|
| `HEALTH_CHECK_INTERVAL` | `300` | Telegram 连接健康检查间隔（秒）|

---

## 七、代码风格与开发约定

1. **文件精简**：核心逻辑集中在 `tgBotV5.py`，工具函数放入 `utils.py`。
2. **命名规范**：函数使用小写加下划线（snake_case），如 `set_account_leverage`、`get_shanghai_time`。
3. **日志格式**：关键推送消息结构化，包含时间、账户、标的、价格/信号/下单参数等。
4. **异常处理**：关键操作均有 `try/except`，异常信息推送日志群组，便于远程排查。
5. **注释语言**：核心函数和关键流程使用中文注释。
6. **环境变量**：所有敏感/可变参数均通过环境变量管理，禁止硬编码。
7. **版本演进**：
   - 修改主程序或新增功能时，注意 `tgBotV5.py`、`tgBotV4.py`、`tgBotV3.py`、`tgBotV2.py` 为独立版本文件。
   - 如果改动需要同步到旧版本，请分别修改对应文件。
   - `supervisord.conf` 决定实际运行哪个版本。
8. **日志截断**：Telegram 单条消息长度限制为 4096 字符，发送前会判断长度并截断。

---

## 八、测试说明

- **当前项目没有正式的单元测试或集成测试文件**（无 `test_*.py`、`pytest.ini`、`tox.ini` 等）。
- 变更后的验证方式主要是：
  1. 本地运行 `python tgBotV5.py` 观察启动日志，确认 Web Dashboard 端口已监听。
  2. 访问 `http://localhost:DASHBOARD_PORT/`，使用 `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD` 登录，确认系统状态、Telegram 状态、OKX 状态、日志等面板正常。
  3. 检查 Telegram 日志群组是否收到启动价格播报和杠杆设置结果。
  4. 向监听频道发送测试信号，观察机器人是否正确解析并执行下单/平仓。
  5. 检查 `data/processed_message_ids.json` 是否正确记录已处理消息 ID。

---

## 九、部署与运维

### 持久化目录

部署时务必挂载以下目录，否则服务重启后 session 和已处理消息 ID 会丢失：

- `data/sessions`：Telegram session 文件
- `data/processed_message_ids.json`：去重缓存
- `logs`：运行日志

### Northflank 部署要点

1. 设置环境变量 `DATA_DIR=/data`。
2. 持久卷挂载到 `/data`。
3. `supervisord.conf` 默认运行 `tgBotV5.py`。
4. 如需从外部访问 Web Dashboard，请在 Northflank 中暴露 `DASHBOARD_PORT`（默认 8000）为公开端口。

### 生成/刷新 Session

当 Telegram session 失效或首次部署时：

```bash
python generate_session_v2.py
```

按提示输入手机号和验证码，生成新的 session 文件并自动更新 `last_session_path.txt`。

### 查看频道 ID

```bash
python list_dialogs.py
```

用于确认 `.env` 中 `TG_CHANNEL_IDS` 与实际频道 ID 一致。

---

## 十、安全注意事项

1. **敏感信息**：Telegram API、OKX API Key/Secret/Passphrase、Bark Key 均通过环境变量注入，禁止写入代码或提交到仓库。
2. **Session 文件**：`.session` 文件包含 Telegram 登录凭证，应妥善保管，避免泄露。
3. **实盘风险**：`OKX1_FLAG=0` 表示实盘交易。修改下单、平仓、杠杆相关逻辑时务必先在模拟盘（`FLAG=1`）测试。
4. **消息幂等**：程序通过 `processed_message_ids.json` 记录已处理消息 ID，防止重复下单。修改去重逻辑时需格外谨慎。
5. **日志内容**：Telegram 日志群组可能包含账户名、订单信息、余额等敏感数据，请确保日志群组仅限受信任人员访问。
6. **Docker 安全**：容器以 root 运行。如需更高安全性，可在 Dockerfile 中创建非 root 用户，但需确保对 `/data`、`/app/logs` 目录有写权限。

---

## 十一、版本差异速查

| 特性 | tgBotV2 | tgBotV3 | tgBotV4 | tgBotV5 |
|------|---------|---------|---------|---------|
| 支持交易对 | BTC、ETH | BTC、ETH、DOGE、SOL | BTC、ETH、DOGE、SOL | BTC、ETH、DOGE、SOL |
| MA 止损双向平仓 | 不支持 | 支持 | 支持（匹配逻辑更宽松）| 支持 |
| 下单量计算 | 固定数量 `FIXED_QTY_*` | 固定数量 `FIXED_QTY_*` | 按保证金比例 `POSITION_RATIO` + 币张转换 | 同 V4 |
| 账户自定义名称 | 不支持 | 不支持 | 支持 `OKX1_ACCOUNT_NAME` | 同 V4 |
| 币张转换 | 否 | 否 | 是，通过 `PublicData.convert_coin_to_contract_size` | 同 V4 |
| 启动价格播报 | BTC、ETH | BTC、ETH、DOGE、SOL | BTC、ETH、DOGE、SOL | BTC、ETH、DOGE、SOL |
| 平仓过滤 | 仅 `pos > 0` | 仅 `pos > 0` | 仅 `pos > 0` | 同 V4 |
| Web Dashboard | 不支持 | 不支持 | 不支持 | 支持 |
| 网页查看日志 | 不支持 | 不支持 | 不支持 | 支持 |
| 网页 Telegram 重新登录 | 不支持 | 不支持 | 不支持 | 支持 |

---

## 十二、给 AI Agent 的工作建议

1. **修改前**：先确认当前实际运行的是哪个版本（检查 `supervisord.conf` 的 `command`）。
2. **修改后**：若改动影响全局行为，建议同步检查 `tgBotV3.py`/`tgBotV2.py` 是否需要类似修复。
3. **不要删除**：`data/sessions` 目录下的 `.session` 文件和 `last_session_path.txt` 是登录凭证，清理时需谨慎。
4. **环境变量默认值**：当前主程序对关键变量（如 `TG_API_ID`、`TG_API_HASH`、`TG_CHANNEL_IDS`）会在缺失时直接退出，不要假设它们有默认值。
5. **新增依赖**：若新增 Python 包，请同时更新 `requirements.txt`。
6. **文档同步**：任何影响日志格式、环境变量、部署方式或运行流程的变更，都应同步更新 `README.md`、`project_log.md` 和本文件。
