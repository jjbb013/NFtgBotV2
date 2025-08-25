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

if not all([TG_API_ID, TG_API_HASH]):
    print('错误：请确保 .env 文件中已配置 TG_API_ID 和 TG_API_HASH')
    exit(1)

TG_API_ID = int(TG_API_ID)

async def main():
    print("--- Telegram 对话列表查看器 ---")
    
    # 查找最新的 session 文件
    sessions = [os.path.join(SESSION_DIR, f) for f in os.listdir(SESSION_DIR) if f.endswith('.session')]
    if not sessions:
        print("错误：在 'data/sessions' 目录下未找到任何 session 文件。")
        print("请先运行 generate_session.py 或 tgBotV2.py 以完成登录。")
        return

    latest_session = max(sessions, key=os.path.getctime)
    print(f"使用最新的 session 文件: {latest_session}")

    client = TelegramClient(latest_session, TG_API_ID, TG_API_HASH)
    
    await client.connect()
    if not await client.is_user_authorized():
        print("错误：该 session 文件未授权或已失效。请重新生成 session。")
        await client.disconnect()
        return

    print("\n正在获取您的对话列表 (最近100个)...")
    
    dialogs = await client.get_dialogs(limit=100)
    
    print("="*50)
    print("{:<15} | {:<40}".format("ID", "标题"))
    print("-"*50)
    
    for dialog in dialogs:
        # is_channel or is_group
        if dialog.is_channel or dialog.is_group:
            print("{:<15} | {:<40}".format(dialog.id, dialog.title))
            
    print("="*50)
    print("\n请检查以上列表，确认您在 .env 文件中配置的 TG_CHANNEL_IDS 是否与这里的 ID 一致。")
    print("注意：私有频道/群组的 ID 通常是一长串以 '-100' 开头的负数。")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
