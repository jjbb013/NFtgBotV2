# Telegram 信号交易机器人

此项目是一个功能强大的 Telegram 信号交易机器人，能够监听指定频道的交易信号，并自动在 OKX 交易所执行相应的开仓和平仓操作。项目支持多账户管理、Docker 一键部署，并具备详细的日志和实时通知功能。

## 最新更新 (v4 - 2025-10-05)

### 新增功能：Telegram Session 有效性监控

为了解决 Telegram Session 因异地登录等原因失效导致机器人掉线的问题，本次更新引入了一个独立的后台监控服务。

- **独立监控脚本**: 新增 `session_validator.py` 脚本，通过 `supervisord` 作为守护进程与主机器人一同运行。
- **定期健康检查**: 该脚本会定期（默认每10分钟）检查当前 `tgBotV4.py` 使用的 `.session` 文件是否仍然有效。
- **实时失效告警**: 一旦检测到 Session 失效，系统会立即通过 **Bark** 发送一条推送通知到您的手机，提醒您需要重新生成 Session 文件。
- **高可用性**: 此功能与主交易逻辑解耦，确保了监控的稳定性和主程序的独立性。

### 如何配置 Session 监控

1.  **确保 `supervisord.conf` 配置正确**:
    `supervisord.conf` 文件中已自动添加了 `[program:session_validator]` 配置块。它会随主程序一同启动。

2.  **添加 Bark 环境变量**:
    为了能接收到 Session 失效的通知，您必须在 `.env` 文件或部署平台的环境变量中添加您的 Bark Key。

    ```
    BARK_KEY="您的Bark Key"
    ```

3.  **(可选) 调整检查频率**:
    您可以通过以下环境变量调整检查频率和失败后的重试延迟：
    - `SESSION_CHECK_INTERVAL`: 每次检查之间的时间间隔（秒），默认为 `600` (10分钟)。
    - `SESSION_RETRY_DELAY`: 检测到失败后，下一次重试前的等待时间（秒），默认为 `3600` (1小时)。

---

## 主要功能与版本历史

### v4 版本 (当前)

- **主程序**: `tgBotV4.py`
- **核心改进**:
    - 引入了上述的 Session 有效性监控机制。
    - 优化了代码结构和日志输出。

### v3 版本 (2025-08-05)

1.  **新增交易标的**:
    *   增加了对 `DOGE-USDT-SWAP` 和 `SOL-USDT-SWAP` 的支持。
    *   需要在环境变量中为新交易对配置下单数量，见下文。
2.  **新增平仓逻辑**:
    *   增加了对 "MA止损" 关键词的识别。当信号中包含此关键词时，机器人将对指定交易对执行 **双向平仓**（无论持有多仓还是空仓，都将平掉）。

### 如何切换回 v2 版本

如果您需要运行旧版 (`tgBotV2.py`)，请修改 `supervisord.conf` 文件：

```ini
[program:tgBotV3]
command=python ./tgBotV3.py
...
```

修改为:

```ini
[program:tgBotV2]
command=python ./tgBotV2.py
...
```

并确保日志文件名也相应修改，然后重新部署。

---

## 持久化存储配置

为了在 Northflank 上实现会话文件和已处理消息ID的持久化存储，您需要配置 `DATA_DIR` 环境变量。Northflank 通常会将持久卷挂载到 `/data` 目录，因此建议将 `DATA_DIR` 设置为 `/data`。

**环境变量:**

*   `DATA_DIR`: 持久化数据存储的根目录。**请务必在 Northflank 部署中将其设置为 `/data`。**

例如，在 Northflank 的服务配置中，您应该添加以下环境变量：

```
DATA_DIR=/data
```

这将确保您的 `session` 文件和 `processed_message_ids.json` 文件存储在持久卷上，从而在服务重启后数据不会丢失。

## 环境变量配置

请确保您已配置所有必要的 Telegram 和 OKX 相关的环境变量。

### 核心环境变量

- `TG_API_ID`: 您的 Telegram API ID。
- `TG_API_HASH`: 您的 Telegram API Hash。
- `TG_LOG_GROUP_ID`: 用于接收机器人运行日志的 Telegram 群组ID。
- `TG_CHANNEL_IDS`: 需要监听信号的 Telegram 频道ID，多个请用逗号分隔。
- `BARK_KEY`: **(v4 新增)** 您的 Bark 推送 Key，用于接收 Session 失效通知。

### OKX 账户环境变量 (以账户1为例)

- `OKX1_API_KEY`
- `OKX1_SECRET_KEY`
- `OKX1_PASSPHRASE`
- `OKX1_FLAG`: 模拟盘设置为 `1`，实盘设置为 `0`。
- `OKX1_LEVERAGE`: 杠杆倍数。
- `OKX1_POSITION_RATIO`: 开仓保证金占总余额的比例 (例如 `0.25` 代表 25%)。
- `OKX1_TP_RATIO`: 止盈比例。
- `OKX1_SL_RATIO`: 止损比例。

*如果您有多个OKX账户，请按 `OKX2_...`, `OKX3_...` 的格式继续添加。*

### 其他可选环境变量

- `SESSION_CHECK_INTERVAL`: **(v4 新增)** Session 检查间隔（秒），默认 `600`。
- `SESSION_RETRY_DELAY`: **(v4 新增)** Session 失效后重试延迟（秒），默认 `3600`。
- `PATCH_MISSING_SIGNALS_INTERVAL`: 历史信号补单检查间隔（秒），默认 `30`。
- `HEALTH_CHECK_INTERVAL`: 主程序健康检查间隔（秒），默认 `300`。

### v3 版本历史环境变量

为了支持新增的交易对，请添加以下环境变量（以OKX1账户为例）：

*   `OKX1_FIXED_QTY_DOGE`: OKX1账户的DOGE下单数量。
*   `OKX1_FIXED_QTY_SOL`: OKX1账户的SOL下单数量。

如果您有多个OKX账户，请相应地添加 `OKX2_FIXED_QTY_DOGE` 等。

### 完整环境变量示例

*   `TG_API_ID`
*   `TG_API_HASH`
*   `TG_LOG_GROUP_ID`
*   `TG_CHANNEL_IDS`
*   `OKX1_API_KEY`
*   `OKX1_SECRET_KEY`
*   `OKX1_PASSPHRASE`
*   `OKX1_FLAG`
*   `OKX1_LEVERAGE`
*   `OKX1_FIXED_QTY_BTC`
*   `OKX1_FIXED_QTY_ETH`
*   `OKX1_FIXED_QTY_DOGE`  **(v3 新增)**
*   `OKX1_FIXED_QTY_SOL`   **(v3 新增)**
*   `OKX1_TP_RATIO`
*   `OKX1_SL_RATIO`
*   `PATCH_MISSING_SIGNALS_INTERVAL`
*   `HEALTH_CHECK_INTERVAL`

请根据您的实际情况配置这些变量。
