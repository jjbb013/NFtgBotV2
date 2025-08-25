import os
import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient

# --- Initial Setup ---
load_dotenv('.env')

# --- Configurable Parameters ---
TG_API_ID = os.getenv('TG_API_ID')
TG_API_HASH = os.getenv('TG_API_HASH')
SESSION_DIR = os.getenv('SESSION_DIR', './data/sessions')
os.makedirs(SESSION_DIR, exist_ok=True)

if not all([TG_API_ID, TG_API_HASH]):
    print('错误：请确保 .env 文件中已配置 TG_API_ID 和 TG_API_HASH')
    exit(1)

TG_API_ID = int(TG_API_ID)

async def main():
    print("--- Telegram Session 生成器 ---")
    
    # 使用手机号作为 session 文件名，方便识别
    phone_number = input("请输入您的 Telegram 手机号 (格式如 +8612345678901): ")
    session_name = f"session_{phone_number.replace('+', '')}"
    session_path = os.path.join(SESSION_DIR, session_name)
    
    print(f"将创建 session 文件: {session_path}.session")

    client = TelegramClient(session_path, TG_API_ID, TG_API_HASH)
    
    await client.start(phone_number)

    me = await client.get_me()
    print(f"登录成功！用户: {me.first_name} {me.last_name or ''}")
    print(f"Session 文件已保存在: {session_path}.session")
    print("现在您可以停止本程序 (Ctrl+C)，然后运行主程序 tgBotV2.py 了。")
    
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
