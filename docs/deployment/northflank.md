# Northflank 部署指南（tgBot Lite）

> 本指南假设你使用当前项目的 `feat/tgBot-lite` 分支（或已合并后的 `main` 分支）。
> 目标：把 tgBot Lite 部署到 Northflank PaaS，使用 Northflank 原生 **MongoDB addon** 做持久化，不再使用 Volume。

---

## 目录

1. [前置条件](#1-前置条件)
2. [总体架构](#2-总体架构)
3. [第一步：准备代码分支](#3-第一步准备代码分支)
4. [第二步：创建 Northflank 项目](#4-第二步创建-northflank-项目)
5. [第三步：创建 MongoDB Addon](#5-第三步创建-mongodb-addon)
6. [第四步：创建 Combined Service](#6-第四步创建-combined-service)
7. [第五步：配置环境变量](#7-第五步配置环境变量)
8. [第六步：暴露端口与健康检查](#8-第六步暴露端口与健康检查)
9. [第七步：部署并查看日志](#9-第七步部署并查看日志)
10. [第八步：登录 Telegram](#10-第八步登录-telegram)
11. [第九步：验证 Dashboard](#11-第九步验证-dashboard)
12. [第十步：发送测试信号](#12-第十步发送测试信号)
13. [升级与回滚](#13-升级与回滚)
14. [常见问题排查](#14-常见问题排查)

---

## 1. 前置条件

- 一个 Northflank 账号（免费套餐可用，但资源有限）。
- GitHub 仓库 `jjbb013/NFtgBotV2` 已推送 `feat/tgBot-lite` 分支。
- 已准备好 Telegram API ID / Hash（从 https://my.telegram.org 获取）。
- 已准备好 OKX API Key / Secret / Passphrase（建议先在模拟盘测试）。
- 可选：Bark Key（iOS 推送）。

> ⚠️ **注意**：Northflank 免费项目默认最多只能运行 **2 个服务/插件**。如果你的现有项目（如 `gemini-b`）已经有 2 个服务，建议新建一个项目来部署 tgBot Lite，或者删除/暂停旧服务。

---

## 2. 总体架构

```text
┌──────────────────────────────────────────────────────────┐
│                    Northflank Project                     │
│  ┌─────────────────────┐      ┌─────────────────────┐   │
│  │  Combined Service   │      │   MongoDB Addon     │   │
│  │  (tgBot Lite)       │◄────►│  (session + IDs)    │   │
│  │  - Build from GitHub│      │                     │   │
│  │  - Run python main.py      │                     │   │
│  │  - Port 8000        │      │                     │   │
│  └─────────────────────┘      └─────────────────────┘   │
└──────────────────────────────────────────────────────────┘
           │
           ▼
    Public URL (https://xxx.code.run)
           │
    ┌──────┴──────┐
    ▼             ▼
 /health      / (Dashboard)
  无需认证    Basic Auth
```

---

## 3. 第一步：准备代码分支

在本地或 GitHub 上确认分支已推送：

```bash
git checkout feat/tgBot-lite
git push -u origin feat/tgBot-lite
```

如果你希望直接部署 `main`，请先把 PR 合并到 `main`，然后 Northflank 里选择 `main` 分支。

---

## 4. 第二步：创建 Northflank 项目

1. 登录 Northflank 控制台：https://app.northflank.com
2. 点击左侧 **Projects** → **Create new project**。
3. 填写：
   - **Project name**：`tgbot-lite`（或你喜欢的名字）
   - **Region**：选择离你最近的区域，例如 `asia-east` / `europe-west`
4. 点击 **Create project**。

---

## 5. 第三步：创建 MongoDB Addon

1. 进入新项目，点击左侧 **Addons** → **Create addon**。
2. 选择 **MongoDB**。
3. 配置：
   - **Name**：`tgbot-mongo`
   - **Version**：`latest`
   - **Billing**：免费套餐选择最小规格（例如 `nf-compute-50`，存储 1024 MB）
   - **External access**：保持关闭（服务内部访问即可）
   - **TLS**：保持关闭（本版本使用普通连接字符串）
4. 点击 **Create addon**。
5. 等待 MongoDB 状态变为 **Running**（通常 1-3 分钟）。
6. 点击进入 addon 详情页，找到 **Connection details**。
7. 复制 **URI**（格式类似）：

```text
mongodb://admin:password@mongodb-tgbot-mongo:27017/tgbot_lite?authSource=admin
```

> 这个 URI 就是后面要设置的 `MONGODB_URI`。

---

## 6. 第四步：创建 Combined Service

1. 在项目里点击 **Create new** → **Combined service**（Build + Deploy 一体）。
2. 基础配置：
   - **Name**：`tgbot-lite`
   - **Description**：`Telegram signal trading bot with dashboard`
3. 源码配置：
   - **Git account**：选择你的 GitHub 账号
   - **Repository**：`jjbb013/NFtgBotV2`
   - **Branch**：`feat/tgBot-lite`（或 `main`）
4. 构建配置：
   - **Build engine**：`Dockerfile`
   - **Dockerfile path**：`/Dockerfile`
   - **Build context**：`/`
5. 部署配置：
   - **Deployment plan**：免费套餐选择最小规格，例如 `nf-compute-20`
   - **Instances**：`1`
   - **Port**：稍后在 Networking 里添加
6. 点击 **Create service**。

> Northflank 会自动拉取代码并构建 Docker 镜像。构建成功后进入部署阶段。

---

## 7. 第五步：配置环境变量

1. 进入 service 详情页，点击顶部 **Environment** 标签。
2. 点击 **Add variable**，逐条添加以下变量：

### 必需变量

| Variable | Value | 说明 |
|----------|-------|------|
| `TG_API_ID` | `你的 Telegram API ID` | 纯数字 |
| `TG_API_HASH` | `你的 Telegram API Hash` | 字符串 |
| `TG_CHANNEL_IDS` | `-1001234567890` | 监听频道 ID，多个用英文逗号分隔 |
| `MONGODB_URI` | `mongodb://...` | 从 MongoDB addon 复制 |
| `DASHBOARD_PASSWORD` | `强密码` | Dashboard 登录密码 |

### 可选变量

| Variable | 默认值 | 说明 |
|----------|--------|------|
| `TG_LOG_GROUP_ID` | 空 | Telegram 日志群组 ID，不填则不发日志 |
| `DASHBOARD_USERNAME` | `admin` | Dashboard 用户名 |
| `DASHBOARD_PORT` | `8000` | 服务端口 |
| `BARK_KEY` | 空 | Bark 推送 key |
| `PATCH_MISSING_SIGNALS_INTERVAL` | `30` | 补单检查间隔（秒） |
| `HEALTH_CHECK_INTERVAL` | `300` | 健康检查间隔（秒） |
| `LOG_BUFFER_SIZE` | `500` | 内存日志缓冲条数 |

### OKX 账户变量（以账户 1 为例，最多 5 个）

| Variable | 说明 |
|----------|------|
| `OKX1_API_KEY` | OKX API Key |
| `OKX1_SECRET_KEY` | OKX Secret Key |
| `OKX1_PASSPHRASE` | OKX Passphrase |
| `OKX1_FLAG` | `0` 实盘，`1` 模拟盘 |
| `OKX1_LEVERAGE` | 杠杆倍数，例如 `10` |
| `OKX1_POSITION_RATIO` | 开仓保证金比例，例如 `0.25` |
| `OKX1_TP_RATIO` | 止盈比例，例如 `0.01` |
| `OKX1_SL_RATIO` | 止损比例，例如 `0.027` |
| `OKX1_ACCOUNT_NAME` | 自定义账户名，例如 `OKX1` |

> 如果要配置第 2 个账户，变量名改为 `OKX2_*`，以此类推。

3. 添加完所有变量后，点击 **Save changes**。

---

## 8. 第六步：暴露端口与健康检查

1. 在 service 详情页，点击 **Networking** 标签。
2. 点击 **Add port**。
   - **Port**：`8000`
   - **Protocol**：`HTTP`
   - 勾选 **Public URL**（如果需要公网访问 Dashboard）
3. 保存后 Northflank 会分配一个类似 `https://p01--tgbot-lite--xxxx.code.run` 的公网 URL。
4. 点击 **Health checks** 标签（或在 Networking 里找到 Health check 设置）。
5. 添加 HTTP health check：
   - **Path**：`/health`
   - **Method**：`GET`
   - **Port**：`8000`
   - **Initial delay**：`10`
   - **Interval**：`30`
   - **Timeout**：`5`
   - **Failure threshold**：`3`
6. 保存。

> `/health` 是未认证接口，Northflank 探针可以正常访问。

---

## 9. 第七步：部署并查看日志

1. 回到 service 详情页，Northflank 会自动重新部署。
2. 等待部署状态变为 **Running / Healthy**。
3. 点击顶部 **Logs** 标签查看启动日志。

正常启动日志应包含：

```text
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
Telegram 登录失败: ...
```

> 首次部署时 Telegram 尚未登录，所以会看到 `Telegram 登录失败` 的日志，这是正常的。

---

## 10. 第八步：登录 Telegram

1. 打开 Northflank 分配的公网 URL，例如：

```text
https://p01--tgbot-lite--xxxx.code.run/login
```

2. 浏览器会弹出 HTTP Basic Auth 窗口，输入：
   - 用户名：`admin`（或你设置的 `DASHBOARD_USERNAME`）
   - 密码：你设置的 `DASHBOARD_PASSWORD`
3. 在登录页面输入你的手机号，格式：`+86138xxxxxxxx`。
4. 点击 **发送验证码**。
5. 在手机 Telegram App 里查看验证码（注意不是短信）。
6. 输入验证码，点击 **确认登录**。
7. 登录成功后，`StringSession` 会自动写入 MongoDB。

> 后续重启服务会自动从 MongoDB 读取 session，无需再次登录。

---

## 11. 第九步：验证 Dashboard

登录 Telegram 后，等待 1-2 分钟让服务重新连接：

1. 访问 `/health`：

```bash
curl https://p01--tgbot-lite--xxxx.code.run/health
```

应返回：

```json
{
  "status": "ok",
  "telegram_connected": true,
  "startup_time": "2026-06-16T..."
}
```

2. 访问首页 `/`，查看：
   - Telegram 连接状态
   - 启动时间
   - 已配置的 OKX 账户列表
   - 最近日志
3. 访问 `/orders`，查看各账户最近订单（实时查询 OKX）。

---

## 12. 第十步：发送测试信号

**强烈建议先在模拟盘测试（`OKX1_FLAG=1`）。**

1. 在监听的 Telegram 频道发送一条测试消息：

```text
执行交易:做多 100USDT 策略当前交易对:BTCUSDT.P
```

2. 观察 Northflank Logs 和 Dashboard 日志页面。
3. 如果一切正常，你会看到：
   - 价格获取
   - 余额/保证金计算
   - 下单参数
   - OKX 返回结果
4. 登录 OKX 模拟盘，确认订单已成交。

---

## 13. 升级与回滚

### 升级代码

1. 本地修改代码并提交到 `feat/tgBot-lite`。
2. 推送到 GitHub：

```bash
git push origin feat/tgBot-lite
```

3. 在 Northflank service 详情页，点击 **Builds** → **Start build**（或等待自动触发，如果你设置了自动构建）。
4. 构建成功后 Northflank 会自动部署新版本。

### 回滚

1. 在 Northflank 进入 service 详情页 → **Deployments**。
2. 找到上一个正常运行的部署版本。
3. 点击 **Rollback** 即可回滚。

---

## 14. 常见问题排查

### Q1: 服务启动后立即退出，日志显示 "无法连接 MongoDB"

- 检查 `MONGODB_URI` 是否正确。
- 确认 MongoDB addon 状态为 **Running**。
- 如果 MongoDB 开启了 TLS，需要把 URI 中的 `mongodb://` 改为 `mongodb+srv://` 或添加 TLS 参数（本版本未做 TLS 适配）。

### Q2: `/health` 返回 401

- 确认健康检查路径是 `/health`，且 Northflank 探针配置中**没有**添加 Basic Auth 凭据。
- `/health` 是本项目的未认证接口。

### Q3: 登录 Telegram 后仍然显示 "Telegram 未连接"

- 登录成功后需要等待服务重新连接（最多几十秒）。
- 检查日志是否有新的错误。
- 确认 `MONGODB_URI` 正确，session 已写入数据库。

### Q4: 下单没有反应

- 检查监听频道 ID 是否正确。
- 检查 OKX API Key/Secret/Passphrase 是否正确，以及是否在模拟盘/实盘。
- 查看日志中的 OKX 返回错误信息。

### Q5: 免费套餐资源不足

- Northflank 免费项目最多 2 个服务/插件。
- 如果现有项目已满，建议新建一个项目部署 tgBot Lite。

### Q6: 如何查看 Dashboard 密码

- Dashboard 密码就是你设置的 `DASHBOARD_PASSWORD` 环境变量。
- 如果忘记，可以在 Northflank Environment 里修改后重新部署。

---

## 附录：最小环境变量清单

```text
TG_API_ID=12345
TG_API_HASH=xxxxxxxxxxxxxxxx
TG_CHANNEL_IDS=-1001234567890
MONGODB_URI=mongodb://admin:password@mongodb-tgbot-mongo:27017/tgbot_lite?authSource=admin
DASHBOARD_PASSWORD=your_strong_password

OKX1_API_KEY=...
OKX1_SECRET_KEY=...
OKX1_PASSPHRASE=...
OKX1_FLAG=1
OKX1_LEVERAGE=10
OKX1_POSITION_RATIO=0.25
OKX1_TP_RATIO=0.01
OKX1_SL_RATIO=0.027
OKX1_ACCOUNT_NAME=OKX1
```

---

> 如有其他问题，优先查看 Northflank Logs 和 Dashboard 日志页面，所有关键事件都会记录在那里。
