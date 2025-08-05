# Northflank 部署说明

此目录包含适配 Northflank 平台的 Telegram 信号交易机器人代码。

## 版本说明

当前默认运行 `tgBotV3.py`。

### v3 版本更新 (2025-08-05)

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

## 其他环境变量

请确保您已配置所有必要的 Telegram 和 OKX 相关的环境变量。

### v3 版本新增环境变量

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
