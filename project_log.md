# 项目日志与规范（project_log.md）

## 一、项目核心功能

1. **多账户支持**：支持遍历所有配置账户，分别处理信号、下单、日志推送等操作。
2. **行情获取**：启动时自动获取 BTC-USDT-SWAP、ETH-USDT-SWAP 最新价格，推送到 Telegram 日志群组。
3. **信号处理**：接收信号后，判断信号有效性，执行下单/平仓操作，并将原始信号、判断结果、下单返回等信息推送日志群组。
4. **杠杆设置**：首次启动时为每个账户的 BTC/ETH 标的设置杠杆倍数（从环境变量读取），并推送设置结果到日志群组。
5. **日志推送**：所有关键操作（行情、信号、下单、杠杆设置等）均推送到 Telegram 日志群组，便于远程监控和对账。
6. **Docker 极简部署**：支持通过 Docker 镜像一键部署，挂载本地 data、logs 目录，加载 .env 环境变量。

---

## 二、代码风格与结构

- **文件精简**：仅保留 `tgBotV2.py`（主逻辑）、`utils.py`（工具函数）、`requirements.txt`、`supervisord.conf`、`start.sh`、`Dockerfile`、`data/sessions`、`logs`、`processed_message_ids.json`、`README.md` 等核心文件。
- **函数命名**：统一使用小写加下划线（snake_case），如 `set_account_leverage`。
- **日志与消息格式**：所有推送消息结构化，包含时间、账户、标的、价格/信号/下单参数等关键信息。
- **环境变量管理**：通过 `.env` 文件或 Docker `--env-file` 参数注入，所有敏感/可变参数均用环境变量管理。
- **异常处理**：关键操作均有 try/except，异常信息推送日志群组，便于远程排查。
- **注释与文档**：核心函数、关键流程均有中文注释，便于维护。

---

## 三、日志格式规范

### 1. 行情推送
```
[行情播报]
时间：2024-06-01 10:00:00（上海）
账户：account1
标的：BTC-USDT-SWAP
价格：68000.12
标的：ETH-USDT-SWAP
价格：3800.56
```

### 2. 信号处理
```
[信号处理]
时间：2024-06-01 10:05:00（上海）
账户：account1
原始信号：xxxxxx
信号判断：做多/做空/无效
下单参数：{...}
下单返回：{...}
```

### 3. 杠杆设置
```
[杠杆设置]
时间：2024-06-01 10:00:01（上海）
账户：account1
标的：BTC-USDT-SWAP
杠杆倍数：20
设置结果：成功/失败，错误信息
```

### 4. 异常/错误
```
[异常告警]
时间：2024-06-01 10:10:00（上海）
账户：account1
操作：下单
错误信息：TimeoutError: ...
```

---

## 四、部署与运维建议

- **Docker 启动命令**：
  ```bash
  docker run -d --name tg-signal-bot \
    -v $PWD/data:/app/data \
    -v $PWD/logs:/app/logs \
    --env-file $PWD/.env \
    willpan013/tg-signal-bot:latest
  ```
- **.env 文件管理**：敏感信息（如 API KEY、杠杆倍数等）全部写入 .env，避免硬编码。
- **日志持久化**：挂载 logs 目录，便于后续排查。
- **session 文件管理**：挂载 data/sessions，避免登录失效。

---

## 五、开发与沟通约定

- **所有新功能、风格变更、日志格式调整，需同步更新本文件。**
- **如有疑问，优先查阅本文件，保持团队风格统一。**

---

## 六、tgBot Lite 重构记录（2026-06-16）

### 重构目标

- 轻量化、模块化、适配 Northflank PaaS，保留轻量 Dashboard。

### 主要变更

1. **删除历史文件**：`tgBotV2.py`、`tgBotV3.py`、`tgBotV4.py`、`okx_account.py`、`utils.py`、`supervisord.conf`、`start.sh`。
2. **新增模块**：
   - `config.py`：统一环境变量管理。
   - `db.py`：MongoDB 持久化。
   - `core/helpers.py`、`core/account.py`、`core/signals.py`、`core/processor.py`：职责分离。
   - `telegram_client.py`：Telethon 客户端 + 网页登录向导。
   - `web/app.py` + `templates/` + `static/`：FastAPI Dashboard。
   - `main.py`：uvicorn 入口。
3. **持久化方式**：
   - Telegram 使用 `StringSession`，session 字符串存入 MongoDB。
   - 已处理消息 ID 存入 MongoDB。
   - 不再依赖 Volume / `DATA_DIR`。
4. **启动方式**：
   - 去掉 supervisor，`Dockerfile` 直接运行 `python main.py`。
   - 单进程，日志输出到 stdout。
5. **Dashboard**：
   - HTTP Basic Auth。
   - `/health` 无需认证，供 Northflank 探针使用。
   - 状态页、实时订单、内存日志、Telegram 登录向导。
6. **依赖调整**：
   - 移除 `sqlalchemy`。
   - 新增 `pymongo`。
   - 保留 `fastapi`、`jinja2`、`uvicorn`、`python-multipart`。

### 部署注意

- Northflank 上需创建 MongoDB addon，设置 `MONGODB_URI`。
- 暴露 HTTP 端口 `8000`，健康检查路径 `/health`。
- 首次部署后访问 `/login` 完成 Telegram 登录。
