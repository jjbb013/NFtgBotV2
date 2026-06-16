import asyncio
import logging
import sys

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

import config
import db
from core import processor, signals
from core.account import OKXAccount

logger = logging.getLogger(__name__)

client = None
_pending_login = {}
_login_lock = asyncio.Lock()
_background_tasks = []

accounts = [OKXAccount(cfg) for cfg in config.get_accounts()]


async def init_processed_ids():
    ids = db.load_processed_ids()
    for channel_id in config.CHANNEL_IDS:
        ids.setdefault(channel_id, set())
        try:
            async for message in client.iter_messages(channel_id, limit=50):
                if message:
                    ids[channel_id].add(message.id)
        except Exception as e:
            logger.error(f"初始化 channel {channel_id} 消息 ID 失败: {e}")
    db.save_processed_ids(ids)
    return ids


async def set_leverage_for_all():
    logger.info("正在为所有账户设置杠杆...")
    for account in accounts:
        for symbol in ["BTC", "ETH"]:
            await account.set_leverage(symbol, account.cfg['LEVERAGE'])


async def send_startup_prices():
    logger.info("启动价格播报...")
    if not config.TG_LOG_GROUP_ID:
        return
    for symbol in ["BTC", "ETH", "DOGE", "SOL"]:
        price = accounts[0].get_price(symbol) if accounts else None
        if price:
            try:
                await client.send_message(
                    config.TG_LOG_GROUP_ID,
                    f"【开盘价】{symbol}-USDT-SWAP: {price}",
                )
            except Exception as e:
                logger.error(f"启动价格播报发送失败: {e}")


async def health_check():
    while True:
        await asyncio.sleep(config.HEALTH_CHECK_INTERVAL)
        try:
            if not client.is_connected():
                raise ConnectionError("Client disconnected")
            await client.get_me()
            processor.record_log("【健康检查】Telegram 连接正常")
        except Exception as e:
            logger.error(f"【健康检查】连接异常: {e}。准备重启...")
            await client.disconnect()
            sys.exit(1)


async def check_and_patch_missing_signals():
    while True:
        await asyncio.sleep(config.PATCH_MISSING_SIGNALS_INTERVAL)
        processor.record_log("【定时补单检查】启动...")
        ids = db.load_processed_ids()
        try:
            for channel_id in config.CHANNEL_IDS:
                async for msg in client.iter_messages(channel_id, limit=20):
                    if not (msg and msg.text):
                        continue
                    if msg.id in ids.get(channel_id, set()):
                        continue
                    ids.setdefault(channel_id, set()).add(msg.id)
                    db.save_processed_ids(ids)
                    action, symbol = signals.extract_trade_info(msg.text)
                    if action and symbol:
                        await processor.process_open_signal(action, symbol, f"补单: {msg.text}", accounts)
                    close_type, close_symbol = signals.extract_close_signal(msg.text)
                    if close_type and close_symbol:
                        await processor.process_close_signal(close_type, close_symbol, f"补单: {msg.text}", accounts)
        except Exception as e:
            logger.error(f"补单检查异常: {e}")


@events.register(events.NewMessage(chats=config.CHANNEL_IDS))
async def handler(event):
    msg_text = event.message.text or ''
    ids = db.load_processed_ids()
    if event.id in ids.get(event.chat_id, set()):
        return
    ids.setdefault(event.chat_id, set()).add(event.id)
    db.save_processed_ids(ids)

    action, symbol = signals.extract_trade_info(msg_text)
    if action and symbol:
        async with processor.signal_lock:
            await processor.process_open_signal(action, symbol, msg_text, accounts)
    close_type, close_symbol = signals.extract_close_signal(msg_text)
    if close_type and close_symbol:
        async with processor.signal_lock:
            await processor.process_close_signal(close_type, close_symbol, msg_text, accounts)


async def _run_client():
    """在 client 已授权并连接后，注册处理器并启动后台任务。"""
    global _background_tasks
    client.add_event_handler(handler)

    logger.info(f"已登录 Telegram，监听频道: {config.CHANNEL_IDS}")
    await init_processed_ids()
    await set_leverage_for_all()
    await send_startup_prices()

    # 取消旧的后台任务（如果存在）
    for task in _background_tasks:
        task.cancel()
    _background_tasks = [
        asyncio.create_task(check_and_patch_missing_signals()),
        asyncio.create_task(health_check()),
    ]

    await client.run_until_disconnected()


async def start_client():
    global client
    session_str = db.load_session_string()
    client = TelegramClient(
        StringSession(session_str),
        config.TG_API_ID,
        config.TG_API_HASH,
    )
    processor.set_telegram_client(client)

    try:
        await client.start()
    except Exception as e:
        logger.error(f"Telegram 登录失败: {e}")
        return

    if not session_str:
        new_session = client.session.save()
        db.save_session_string(new_session)
        logger.info("已保存新的 Telegram StringSession 到 MongoDB")

    await _run_client()


async def _ensure_connected_client():
    """确保有一个已连接（未授权也可）的 client 实例。"""
    global client
    if client is None:
        client = TelegramClient(
            StringSession(),
            config.TG_API_ID,
            config.TG_API_HASH,
        )
    if not client.is_connected():
        await client.connect()
    processor.set_telegram_client(client)


async def start_login(phone):
    async with _login_lock:
        try:
            await _ensure_connected_client()
            result = await client.send_code_request(phone)
            _pending_login['phone'] = phone
            _pending_login['phone_code_hash'] = result.phone_code_hash
            return {'success': True, 'phone_code_hash': result.phone_code_hash}
        except Exception as e:
            logger.error(f"发送验证码失败: {e}")
            return {'success': False, 'error': str(e)}


async def confirm_login(phone, code, password=None):
    async with _login_lock:
        if _pending_login.get('phone') != phone:
            return {'success': False, 'error': '请先发送验证码'}
        try:
            try:
                await client.sign_in(phone, code, phone_code_hash=_pending_login['phone_code_hash'])
            except SessionPasswordNeededError:
                if not password:
                    return {
                        'success': False,
                        'need_password': True,
                        'error': '已开启两步验证，请输入密码',
                    }
                await client.sign_in(password=password)

            session_str = client.session.save()
            db.save_session_string(session_str)
            _pending_login.clear()
            processor.set_telegram_client(client)

            # 启动监听和后台任务
            asyncio.create_task(_run_client())

            return {'success': True, 'session_saved': True}
        except Exception as e:
            logger.error(f"登录确认失败: {e}")
            return {'success': False, 'error': str(e)}


def is_connected():
    return client.is_connected() if client else False
