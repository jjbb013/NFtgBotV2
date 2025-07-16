# Northflank 部署说明

此目录包含适配 Northflank 平台的 Telegram 信号交易机器人代码。

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

请确保您已配置所有必要的 Telegram 和 OKX 相关的环境变量，例如：

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
*   `OKX1_TP_RATIO`
*   `OKX1_SL_RATIO`
*   `PATCH_MISSING_SIGNALS_INTERVAL`
*   `HEALTH_CHECK_INTERVAL`

请根据您的实际情况配置这些变量。