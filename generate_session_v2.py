import os
import asyncio
import subprocess
from dotenv import load_dotenv
from telethon import TelegramClient

# --- Initial Setup ---
load_dotenv('.env')

# --- Configurable Parameters ---
TG_API_ID = os.getenv('TG_API_ID')
TG_API_HASH = os.getenv('TG_API_HASH')
SESSION_DIR = os.getenv('SESSION_DIR', './data/sessions')
os.makedirs(SESSION_DIR, exist_ok=True)

# --- Path for last session record ---
# Note: The path is constructed relative to the project root where tgBotV4.py runs
LAST_SESSION_PATH_FILE = os.path.join(os.path.dirname(SESSION_DIR), 'last_session_path.txt')


if not all([TG_API_ID, TG_API_HASH]):
    print('错误：请确保 .env 文件中已配置 TG_API_ID 和 TG_API_HASH')
    exit(1)

TG_API_ID = int(TG_API_ID)

async def main():
    print("--- Telegram Session 生成器 V2 ---")

    # 清空旧的 session 文件
    print(f"正在清空目录 {SESSION_DIR} 中的旧 session 文件...")
    cleared_count = 0
    for filename in os.listdir(SESSION_DIR):
        if filename.endswith('.session'):
            file_path = os.path.join(SESSION_DIR, filename)
            try:
                os.remove(file_path)
                print(f"已删除: {filename}")
                cleared_count += 1
            except Exception as e:
                print(f"删除 {filename} 失败: {e}")
    print(f"共清空 {cleared_count} 个旧 session 文件。")
    
    # 使用手机号作为 session 文件名，方便识别
    phone_number = input("请输入您的 Telegram 手机号 (格式如 +8612345678901): ")
    session_name = f"session_{phone_number.replace('+', '')}"
    session_path_without_ext = os.path.join(SESSION_DIR, session_name)
    
    # This is the relative path that tgBotV4.py will use
    relative_session_path = f"./data/sessions/{session_name}.session"
    
    print(f"将创建 session 文件: {relative_session_path}")

    client = TelegramClient(session_path_without_ext, TG_API_ID, TG_API_HASH)
    
    try:
        await client.start(phone_number)

        me = await client.get_me()
        print(f"登录成功！用户: {me.first_name} {me.last_name or ''}")
        print(f"Session 文件已保存在: {relative_session_path}")
        
        # 自动更新 last_session_path.txt
        print(f"正在更新会话记录文件: {LAST_SESSION_PATH_FILE}")
        with open(LAST_SESSION_PATH_FILE, 'w', encoding='utf-8') as f:
            f.write(relative_session_path)
        print("会话记录文件更新成功。")

    except Exception as e:
        print(f"创建 session 失败: {e}")
        return # Exit if session creation fails
    finally:
        if client.is_connected():
            await client.disconnect()
            print("Telegram 客户端已断开连接。")

    # 询问是否重启
    restart_choice = input("是否立即重启 tgBotV4 服务? (y/n): ").lower()
    if restart_choice == 'y':
        print("正在执行 ./start.sh 以重启服务...")
        try:
            # 确保 start.sh 有执行权限
            os.chmod('./start.sh', 0o755)
            # 使用 subprocess 执行 shell 脚本
            subprocess.run(['./start.sh'], check=True)
            print("服务重启命令已执行。请检查 supervisor 日志确认状态。")
        except FileNotFoundError:
            print("错误: start.sh 脚本未找到。请确认脚本位于当前目录。")
        except subprocess.CalledProcessError as e:
            print(f"错误: 执行 start.sh 脚本失败，返回码: {e.returncode}")
        except Exception as e:
            print(f"执行 start.sh 时发生未知错误: {e}")
    else:
        print("操作完成。您可以稍后手动运行 ./start.sh 来启动服务。")


if __name__ == '__main__':
    asyncio.run(main())
