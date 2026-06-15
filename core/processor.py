import asyncio
import json
import logging
from collections import deque

import okx.PublicData as PublicData

import config
from core.helpers import get_shanghai_time, send_bark_notification

logger = logging.getLogger(__name__)
signal_lock = asyncio.Lock()
log_buffer = deque(maxlen=config.LOG_BUFFER_SIZE)

_telegram_client = None


def set_telegram_client(client):
    global _telegram_client
    _telegram_client = client


def record_log(message):
    ts = get_shanghai_time()
    line = f"[{ts}] {message}"
    log_buffer.append(line)
    logger.info(message)


async def send_telegram_log(text):
    if not config.TG_LOG_GROUP_ID or not _telegram_client:
        return
    try:
        if len(text) > 4090:
            text = text[:4000] + "\n...(消息过长，已截断)"
        await _telegram_client.send_message(config.TG_LOG_GROUP_ID, text)
    except Exception as e:
        logger.error(f"发送 Telegram 日志失败: {e}")


async def convert_coin_to_contract_size(inst_id, px, sz, flag):
    try:
        api = PublicData.PublicAPI(flag=flag)
        resp = api.get_convert_contract_coin(
            instId=inst_id,
            px=str(px),
            sz=str(sz),
            type="1",
            unit="usds",
        )
        if resp.get('code') == '0' and resp.get('data'):
            return float(resp['data'][0]['sz'])
        logger.error(f"币张转换失败: {resp.get('msg')}")
    except Exception as e:
        logger.error(f"币张转换异常: {e}")
    return None


async def process_open_signal(action, symbol, msg_text, accounts):
    log_header = "【补单】" if "补单" in msg_text else "【实时信号】"
    record_log(f"{log_header} {action} {symbol}\n原始信息: {msg_text}")

    reference_price = accounts[0].get_price(symbol) if accounts else None
    if not reference_price:
        err = f"无法获取 {symbol} 市场价格，跳过开仓"
        record_log(err)
        await send_telegram_log(err)
        return

    for account in accounts:
        balance = account.get_balance()
        if balance is None:
            err = f"无法获取账户 {account.name} 余额，跳过"
            record_log(err)
            await send_telegram_log(err)
            continue

        margin = balance * account.cfg['POSITION_RATIO']
        leverage = account.cfg['LEVERAGE']
        order_value = margin * leverage
        inst_id = f"{symbol.upper()}-USDT-SWAP"
        size = await convert_coin_to_contract_size(inst_id, reference_price, order_value, account.flag)
        if size is None:
            err = f"{account.name} 币张转换失败，跳过"
            record_log(err)
            await send_telegram_log(err)
            continue

        order_log = (
            f"--- {account.name} 下单计算 ---\n"
            f"余额: {balance:.4f} USDT\n"
            f"保证金: {margin:.4f} USDT\n"
            f"杠杆: {leverage}x\n"
            f"开仓价: {reference_price:.4f}\n"
            f"开仓方向: {action}\n"
            f"开仓张数: {size:.4f}\n"
            f"-------------------------"
        )
        record_log(order_log)

        result = await account.place_order(action, symbol, size)

        full_log = f"{order_log}\n服务器响应: {json.dumps(result, ensure_ascii=False, indent=2)}"
        await send_telegram_log(full_log)

        bark_title = f"{'✅' if result['success'] else '⚠️'} {account.name} {action} {symbol}"
        send_bark_notification(bark_title, full_log)


async def process_close_signal(close_type, symbol, msg_text, accounts):
    log_header = "【补单】" if "补单" in msg_text else "【实时信号】"
    if not symbol:
        err = f"平仓信号 ({close_type}) 未能提取交易对，跳过"
        record_log(f"{log_header} {err}\n原始信息: {msg_text}")
        await send_telegram_log(err)
        send_bark_notification("⚠️ 平仓失败 ⚠️", err)
        return

    record_log(f"{log_header} 平仓 {close_type} {symbol}\n原始信息: {msg_text}")
    for account in accounts:
        result = await account.close_positions(symbol, close_type)
        full_log = (
            f"账户: {account.name}\n"
            f"平仓方向: {close_type} {symbol}\n"
            f"结果: {json.dumps(result, ensure_ascii=False, indent=2)}"
        )
        record_log(full_log)
        await send_telegram_log(full_log)
        send_bark_notification(
            f"Tg信号策略平仓-{symbol}",
            full_log,
        )
