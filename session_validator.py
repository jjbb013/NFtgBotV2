import os
import asyncio
import logging
import time
import requests
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors.rpcerrorlist import AuthKeyUnregisteredError, UserDeactivatedError, SessionRevokedError

# --- 初始设置 ---
load_dotenv('.env')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('SessionValidator')

# --- 从环境变量加载配置 ---
TG_API_ID = os.getenv('TG_API_ID')
TG_API_HASH = os.getenv('TG_API_HASH')
BARK_KEY = os.getenv('BARK_KEY')
CHECK_INTERVAL_SECONDS = int(os.getenv('SESSION_CHECK_INTERVAL', 600)) # 默认10分钟检查一次
RETRY_DELAY_SECONDS = int(os.getenv('SESSION_RETRY_DELAY', 3600)) # 默认失败后1小时再试

# --- 检查关键配置 ---
if not all([TG_API_ID, TG_API_HASH, BARK_KEY]):
    logger.error('关键环境变量 TG_API_ID, TG_API_HASH, BARK_KEY 未配置')
    exit(1)

# --- Session 文件路径 ---
LAST_SESSION_PATH_FILE = os.path.join(os.path.dirname(__file__), 'data', 'last_session_path.txt')

def get_session_file_path():
    """从 data/last_session_path.txt 读取当前的 session 文件路径"""
    try:
        with open(LAST_SESSION_PATH_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.error(f"Session 路径文件未找到: {LAST_SESSION_PATH_FILE}")
        return None

def send_bark_notification(session_path):
    """发送 Bark 通知"""
    if not BARK_KEY:
        logger.warning("BARK_KEY 未配置，无法发送通知。")
        return

    session_name = os.path.basename(session_path)
    title = "🚨 Telegram Session 失效警告"
    body = f"您的 Telegram session 文件 ({session_name}) 已失效，请重新登录以确保机器人正常运行。"
    url = f"https://api.day.app/{BARK_KEY}/{title}/{body}"

    try:
        response = requests.post(url)
        response.raise_for_status()
        logger.info(f"成功发送 Bark 通知: Session {session_name} 失效")
    except requests.exceptions.RequestException as e:
        logger.error(f"发送 Bark 通知失败: {e}")

async def validate_session():
    """核心的 Session 验证逻辑"""
    session_path = get_session_file_path()
    if not session_path:
        logger.error("无法获取 session 文件路径，验证任务暂停。")
        return False

    logger.info(f"正在检查 session 文件: {session_path}")
    client = TelegramClient(session_path, int(TG_API_ID), TG_API_HASH)

    try:
        await client.connect()
        if await client.is_user_authorized():
            logger.info(f"Session ({os.path.basename(session_path)}) 验证通过，状态正常。")
            return True
        else:
            logger.warning(f"Session ({os.path.basename(session_path)}) 未授权。")
            return False
    except (AuthKeyUnregisteredError, UserDeactivatedError, SessionRevokedError) as e:
        logger.error(f"Session ({os.path.basename(session_path)}) 已失效或被撤销: {e}")
        return False
    except Exception as e:
        logger.error(f"连接或验证 session 时发生未知错误: {e}")
        return False # 在不确定的情况下也认为是失败
    finally:
        if client.is_connected():
            await client.disconnect()

async def main():
    """主循环，定期执行验证"""
    logger.info("Session 验证服务已启动。")
    while True:
        is_valid = await validate_session()
        if not is_valid:
            session_path = get_session_file_path()
            if session_path:
                send_bark_notification(session_path)
            logger.info(f"Session 失效，将在 {RETRY_DELAY_SECONDS / 60} 分钟后重试...")
            await asyncio.sleep(RETRY_DELAY_SECONDS)
        else:
            logger.info(f"下次检查将在 {CHECK_INTERVAL_SECONDS / 60} 分钟后进行。")
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("服务已手动停止。")
