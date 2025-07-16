#!/bin/bash

set -e

echo "=== Telegram 交易机器人启动脚本 ==="

# 创建必要目录
mkdir -p /data/sessions /data/logs
chmod 755 /data /data/sessions /data/logs

# 启动supervisord，管理tgBotV2.py进程
exec supervisord -c /app/supervisord.conf 