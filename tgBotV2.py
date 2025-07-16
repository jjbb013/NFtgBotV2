import os
import sys
import time
import asyncio
import logging
import re
from datetime import datetime
import json
from dotenv import load_dotenv
from telethon.sync import TelegramClient
from telethon import events

from utils import get_shanghai_time, send_bark_notification, build_order_params, set_account_leverage
import okx.Trade as Trade
import okx.MarketData as MarketData
import okx.Account as Account

# --- Initial Setup ---
load_dotenv('.env')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('tgBotV2')

# --- Globals ---
signal_lock = asyncio.Lock()

# --- Configurable Parameters ---
TG_API_ID = os.getenv('TG_API_ID')
TG_API_HASH = os.getenv('TG_API_HASH')
TG_LOG_GROUP_ID = os.getenv('TG_LOG_GROUP_ID')
TG_CHANNEL_IDS = os.getenv('TG_CHANNEL_IDS', '')
PATCH_MISSING_SIGNALS_INTERVAL = int(os.getenv('PATCH_MISSING_SIGNALS_INTERVAL', 30))
HEALTH_CHECK_INTERVAL = int(os.getenv('HEALTH_CHECK_INTERVAL', 300))

if not all([TG_API_ID, TG_API_HASH, TG_CHANNEL_IDS]):
    logger.error('关键环境变量 TG_API_ID, TG_API_HASH, TG_CHANNEL_IDS 未配置')
    sys.exit(1)

TG_API_ID = int(TG_API_ID)
TG_LOG_GROUP_ID = int(TG_LOG_GROUP_ID) if TG_LOG_GROUP_ID else None
CHANNEL_IDS = [int(cid.strip()) for cid in TG_CHANNEL_IDS.split(',') if cid.strip()]

# --- Session Management ---
SESSION_DIR = os.getenv('SESSION_DIR', './data/sessions')
os.makedirs(SESSION_DIR, exist_ok=True)
LAST_SESSION_PATH_FILE = os.path.join(SESSION_DIR, '../last_session_path.txt')

def get_session_file():
    if os.path.exists(LAST_SESSION_PATH_FILE):
        with open(LAST_SESSION_PATH_FILE, 'r', encoding='utf-8') as f:
            session_path = f.read().strip()
            logger.info(f'自动复用上次 session 文件: {session_path}')
            return session_path

    sessions = [f for f in os.listdir(SESSION_DIR) if f.endswith('.session')]
    if not sessions:
        logger.info('未检测到 session 文件，将新建登录')
        new_session = os.path.join(SESSION_DIR, f'session_{int(time.time())}.session')
        with open(LAST_SESSION_PATH_FILE, 'w', encoding='utf-8') as f:
            f.write(new_session)
        return new_session

    logger.info('检测到以下 Telegram session 文件：')
    for idx, s in enumerate(sessions):
        logger.info(f'{idx+1}: {s}')

    if not sys.stdout.isatty():
        logger.info("非交互式环境，自动选择第一个 session")
        choice = '1'
    else:
        choice = input('请选择要使用的 session 文件编号，或输入 n 新建登录: ')

    if choice.isdigit() and 1 <= int(choice) <= len(sessions):
        session_path = os.path.join(SESSION_DIR, sessions[int(choice)-1])
    else:
        session_path = os.path.join(SESSION_DIR, f'session_{int(time.time())}.session')
    
    with open(LAST_SESSION_PATH_FILE, 'w', encoding='utf-8') as f:
        f.write(session_path)
    return session_path

session_file = get_session_file()
client = TelegramClient(session_file, TG_API_ID, TG_API_HASH)

# --- Account and Data ---
def get_test_accounts():
    accounts = []
    for i in range(1, 6):
        prefix = f'OKX{i}_'
        if all(os.getenv(prefix + k) for k in ['API_KEY', 'SECRET_KEY', 'PASSPHRASE']):
            accounts.append({
                'account_idx': i, 'account_name': f'OKX{i}',
                'API_KEY': os.getenv(prefix + 'API_KEY'),
                'SECRET_KEY': os.getenv(prefix + 'SECRET_KEY'),
                'PASSPHRASE': os.getenv(prefix + 'PASSPHRASE'),
                'FLAG': os.getenv(prefix + 'FLAG', '1')
            })
    logger.info(f"共加载 {len(accounts)} 个有效OKX账户")
    return accounts

TEST_ACCOUNTS = get_test_accounts()
PROCESSED_IDS_FILE = os.path.join(DATA_DIR, 'processed_message_ids.json')

def load_processed_ids():
    try:
        with open(PROCESSED_IDS_FILE, 'r', encoding='utf-8') as f:
            return {int(k): set(v) for k, v in json.load(f).items()}
    except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
        logger.warning(f"加载消息ID缓存失败 ({e})，将创建新的缓存。")
        return {}

def save_processed_ids(ids):
    try:
        with open(PROCESSED_IDS_FILE, 'w', encoding='utf-8') as f:
            json.dump({k: list(v) for k, v in ids.items()}, f, indent=2)
    except Exception as e:
        logger.error(f"保存消息ID缓存失败: {e}")

PROCESSED_MESSAGE_IDS = load_processed_ids()

# --- Signal Extraction (from root tgBotV2.py) ---
def extract_trade_info(message):
    logger.debug(f"正在从消息中提取交易信息: {message[:100]}...")
    close_keywords = ['空止盈', '空止损', '多止盈', '多止损', '平多', '平空']
    if any(keyword in message for keyword in close_keywords):
        return None, None
    
    action_pattern = r"执行交易[:：]?(.+?)(?= \d+\.\d+\w+)"
    action_match = re.search(action_pattern, message)
    symbol_pattern = r"策略当前交易对[:：]?(\w+USDT\.P)"
    symbol_match = re.search(symbol_pattern, message)
    
    if action_match and symbol_match:
        action_text = action_match.group(1).strip()
        symbol = symbol_match.group(1).replace('USDT.P', '')
        action = '做多' if '做多' in action_text or '买入' in action_text else '做空'
        logger.info(f"精确格式匹配成功 - 动作: {action}, 币种: {symbol}")
        return action, symbol
    
    patterns = {
        '做多': [r'做多\s*([A-Z]+)', r'([A-Z]+)\s*做多', r'买入\s*([A-Z]+)', r'([A-Z]+)\s*买入', r'LONG\s*([A-Z]+)', r'([A-Z]+)\s*LONG'],
        '做空': [r'做空\s*([A-Z]+)', r'([A-Z]+)\s*做空', r'卖出\s*([A-Z]+)', r'([A-Z]+)\s*卖出', r'SHORT\s*([A-Z]+)', r'([A-Z]+)\s*SHORT']
    }
    for action, pattern_list in patterns.items():
        for pattern in pattern_list:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                symbol = match.group(1).upper()
                logger.info(f"通用格式匹配成功 - 动作: {action}, 币种: {symbol}")
                return action, symbol
    return None, None

def extract_close_signal(message):
    logger.debug(f"正在从消息中提取平仓信号: {message[:100]}...")
    if any(kw in message for kw in ['空止盈', '空止损', '平空']):
        close_type = 'short'
    elif any(kw in message for kw in ['多止盈', '多止损', '平多']):
        close_type = 'long'
    else:
        return None, None
    
    symbol_match = re.search(r'([A-Z]+)', message)
    if symbol_match:
        symbol = symbol_match.group(1).upper().replace('USDT.P', '').replace('USDT','')
        logger.info(f"检测到平仓信号 ({close_type}): {symbol}")
        return close_type, symbol
    return close_type, None

# --- OKX & Bark Logic ---
def get_order_size(account_idx, symbol):
    coin = symbol.split('-')[0]
    val = os.getenv(f"OKX{account_idx}_FIXED_QTY_{coin}")
    return float(val) if val else None

def get_latest_market_price(symbol):
    try:
        api = MarketData.MarketAPI(debug=False)
        response = api.get_ticker(instId=f"{symbol.upper()}-USDT-SWAP")
        if response['code'] == '0':
            return float(response['data'][0]['last'])
        logger.error(f"获取 {symbol} 价格失败: {response['msg']}")
    except Exception as e:
        logger.error(f"获取 {symbol} 价格异常: {e}")
    return None

def build_bark_content(signal, account_name, entry_price, size, margin, take_profit, stop_loss, clOrdId, okx_resp=None, error_msg=None):
    now = get_shanghai_time()
    lines = [f"账户: {account_name}", f"交易标的: {signal['symbol']}", f"信号类型: {signal['action']}", f"入场价格: {entry_price:.4f}", f"委托数量: {size:.4f}", f"保证金: {margin} USDT", f"止盈价格: {take_profit:.4f}", f"止损价格: {stop_loss:.4f}", f"客户订单ID: {clOrdId}", f"时间: {now}"]
    if error_msg: lines.extend(["⚠️ 下单失败 ⚠️", f"错误: {error_msg}"])
    if okx_resp: lines.extend([f"服务器响应代码: {okx_resp.get('code', '')}", f"服务器响应消息: {okx_resp.get('msg', '')}"])
    return "\n".join(lines)

def build_close_bark_content(close_type, symbol, account_name, close_results, okx_resp=None, error_msg=None):
    now = get_shanghai_time()
    lines = [f"账户: {account_name}", f"交易标的: {symbol}", f"信号类型: 平仓{close_type}", f"平仓结果: {len(close_results)} 个持仓", f"时间: {now}"]
    if close_results: [lines.append(f"- {res['pos_side']}: {res['size']} (订单ID: {res['order_id']})") for res in close_results]
    if error_msg: lines.extend(["⚠️ 平仓失败 ⚠️", f"错误: {error_msg}"])
    if okx_resp: lines.extend([f"服务器响应代码: {okx_resp.get('code', '')}", f"服务器响应消息: {okx_resp.get('msg', '')}"])
    return "\n".join(lines)

async def place_okx_order(account, action, symbol, size):
    try:
        api = Trade.TradeAPI(account['API_KEY'], account['SECRET_KEY'], account['PASSPHRASE'], False, account['FLAG'])
        price = get_latest_market_price(symbol)
        if not price: return {"success": False, "error_msg": "无法获取市场价格"}

        tp_ratio = float(os.getenv(f"OKX{account['account_idx']}_TP_RATIO", '0.01'))
        sl_ratio = float(os.getenv(f"OKX{account['account_idx']}_SL_RATIO", '0.027'))
        
        side, pos_side = ('buy', 'long') if action == '做多' else ('sell', 'short')
        tp_price = price * (1 + (tp_ratio if side == 'buy' else -tp_ratio))
        sl_price = price * (1 - (sl_ratio if side == 'buy' else -sl_ratio))

        params = build_order_params(f"{symbol}-USDT-SWAP", side, price, size, pos_side, round(tp_price, 4), round(sl_price, 4))
        logger.info(f"下单参数: {json.dumps(params, indent=2)}")
        resp = api.place_order(**params)
        logger.info(f"下单返回: {json.dumps(resp, indent=2)}")

        if resp['code'] == '0' and resp['data'][0]['sCode'] == '0':
            return {"success": True, "market_price": price, "margin": round(price * size / int(os.getenv(f"OKX{account['account_idx']}_LEVERAGE", 10)), 4), "take_profit": tp_price, "stop_loss": sl_price, "clOrdId": params['clOrdId'], "okx_resp": resp}
        else:
            return {"success": False, "error_msg": resp['data'][0]['sMsg'], "okx_resp": resp}
    except Exception as e:
        logger.error(f"下单异常: {e}")
        return {"success": False, "error_msg": str(e)}

async def close_okx_position(account, symbol, close_type):
    try:
        acc_api = Account.AccountAPI(account['API_KEY'], account['SECRET_KEY'], account['PASSPHRASE'], False, account['FLAG'])
        trade_api = Trade.TradeAPI(account['API_KEY'], account['SECRET_KEY'], account['PASSPHRASE'], False, account['FLAG'])
        inst_id = f"{symbol.upper()}-USDT-SWAP"
        
        resp = acc_api.get_positions(instId=inst_id)
        if resp['code'] != '0': return {"success": False, "error_msg": "获取持仓失败"}

        results = []
        for pos in resp.get('data', []):
            if float(pos.get('pos', '0')) > 0 and pos.get('posSide') == close_type:
                side = 'sell' if close_type == 'long' else 'buy'
                close_resp = trade_api.place_order(instId=inst_id, tdMode='cross', side=side, posSide=close_type, ordType='market', sz=pos['pos'])
                if close_resp['code'] == '0' and close_resp['data'][0]['sCode'] == '0':
                    results.append({'pos_side': close_type, 'size': pos['pos'], 'order_id': close_resp['data'][0]['ordId']})
        return {"success": True, "close_results": results, "okx_resp": resp}
    except Exception as e:
        logger.error(f"平仓异常: {e}")
        return {"success": False, "error_msg": str(e)}

# --- Signal Processors ---
async def process_open_signal(action, symbol, msg_text):
    log_header = f"【补单】\n原始信息: {msg_text}" if "补单" in msg_text else f"【实时信号】\n原始信息: {msg_text}"
    for account in TEST_ACCOUNTS:
        size = get_order_size(account['account_idx'], symbol)
        if not size: continue
        result = await place_okx_order(account, action, symbol, size)
        bark_title = f"Tg信号策略{action}-{symbol}"
        content = build_bark_content({'symbol': symbol, 'action': action}, account['account_name'], result.get('market_price', 0), size, result.get('margin', 0), result.get('take_profit', 0), result.get('stop_loss', 0), result.get('clOrdId', ''), result.get('okx_resp'), result.get('error_msg'))
        full_log = f"{log_header}\n信号判断: {action} {symbol} (账户: {account['account_name']})\n操作返回: {json.dumps(result, ensure_ascii=False, indent=2)}"
        logger.info(full_log)
        if TG_LOG_GROUP_ID: await client.send_message(TG_LOG_GROUP_ID, full_log)
        send_bark_notification(bark_title, content)

async def process_close_signal(close_type, symbol, msg_text):
    log_header = f"【补单】\n原始信息: {msg_text}" if "补单" in msg_text else f"【实时信号】\n原始信息: {msg_text}"
    for account in TEST_ACCOUNTS:
        result = await close_okx_position(account, symbol, close_type)
        bark_title = f"Tg信号策略平仓-{symbol}"
        content = build_close_bark_content(close_type, symbol, account['account_name'], result.get('close_results', []), result.get('okx_resp'), result.get('error_msg'))
        full_log = f"{log_header}\n信号判断: 平仓 {close_type} {symbol} (账户: {account['account_name']})\n操作返回: {json.dumps(result, ensure_ascii=False, indent=2)}"
        logger.info(full_log)
        if TG_LOG_GROUP_ID: await client.send_message(TG_LOG_GROUP_ID, full_log)
        send_bark_notification(bark_title, content)

# --- Background Tasks ---
async def health_check():
    while True:
        await asyncio.sleep(HEALTH_CHECK_INTERVAL)
        try:
            if not client.is_connected(): raise ConnectionError("Client disconnected")
            await client.get_me()
            logger.info("【健康检查】Telegram 连接正常")
        except Exception as e:
            logger.error(f"【健康检查】连接异常: {e}。准备重启...")
            await client.disconnect()
            sys.exit(1)

async def check_and_patch_missing_signals():
    while True:
        await asyncio.sleep(PATCH_MISSING_SIGNALS_INTERVAL)
        logger.info('【定时补单检查】启动...')
        global PROCESSED_MESSAGE_IDS
        PROCESSED_MESSAGE_IDS = load_processed_ids()
        try:
            for channel_id in CHANNEL_IDS:
                async for msg in client.iter_messages(channel_id, limit=20):
                    if not (msg and msg.text): continue
                    async with signal_lock:
                        if msg.id in PROCESSED_MESSAGE_IDS.get(channel_id, set()): continue
                        PROCESSED_MESSAGE_IDS.setdefault(channel_id, set()).add(msg.id)
                        save_processed_ids(PROCESSED_MESSAGE_IDS)
                        action, symbol = extract_trade_info(msg.text)
                        if action and symbol: await process_open_signal(action, symbol, f"补单: {msg.text}")
                        close_type, close_symbol = extract_close_signal(msg.text)
                        if close_type and close_symbol: await process_close_signal(close_type, close_symbol, f"补单: {msg.text}")
        except Exception as e: logger.error(f"历史消息补单检查异常: {e}")

# --- Main Application ---
@client.on(events.NewMessage(chats=CHANNEL_IDS))
async def handler(event):
    msg_text = event.message.text or ''
    async with signal_lock:
        if event.id in PROCESSED_MESSAGE_IDS.get(event.chat_id, set()): return
        PROCESSED_MESSAGE_IDS.setdefault(event.chat_id, set()).add(event.id)
        save_processed_ids(PROCESSED_MESSAGE_IDS)
        action, symbol = extract_trade_info(msg_text)
        if action and symbol: await process_open_signal(action, symbol, msg_text)
        close_type, close_symbol = extract_close_signal(msg_text)
        if close_type and close_symbol: await process_close_signal(close_type, close_symbol, msg_text)

async def init_processed_ids():
    logger.info("正在初始化消息ID缓存...")
    for channel_id in CHANNEL_IDS:
        PROCESSED_MESSAGE_IDS.setdefault(channel_id, set())
        async for message in client.iter_messages(channel_id, limit=50):
            if message: PROCESSED_MESSAGE_IDS[channel_id].add(message.id)
    save_processed_ids(PROCESSED_MESSAGE_IDS)
    logger.info("消息ID缓存初始化完成。")

async def set_leverage_for_all_accounts():
    logger.info("正在为所有账户设置杠杆...")
    for account in TEST_ACCOUNTS:
        leverage = os.getenv(f"OKX{account['account_idx']}_LEVERAGE", "10")
        for symbol in ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]:
            try:
                result = set_account_leverage(account['API_KEY'], account['SECRET_KEY'], account['PASSPHRASE'], account['FLAG'], symbol, leverage, "cross")
                log_msg = f"【杠杆设置】{account['account_name']} {symbol}: {leverage}x - {result}"
                logger.info(log_msg)
                if TG_LOG_GROUP_ID: await client.send_message(TG_LOG_GROUP_ID, log_msg)
            except Exception as e:
                logger.error(f"【杠杆设置异常】{account['account_name']} {symbol}: {e}")

async def send_startup_symbol_prices():
    logger.info("启动价格播报...")
    for symbol_id in ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]:
        price = get_latest_market_price(symbol_id.split('-')[0])
        if price and TG_LOG_GROUP_ID:
            await client.send_message(TG_LOG_GROUP_ID, f"【开盘价】{symbol_id}: {price}")

async def main():
    await client.start()
    logger.info(f'已登录 Telegram，监听频道: {CHANNEL_IDS}')
    await init_processed_ids()
    await set_leverage_for_all_accounts()
    await send_startup_symbol_prices()
    asyncio.create_task(check_and_patch_missing_signals())
    asyncio.create_task(health_check())
    logger.info("机器人启动完成，开始监听信号...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    try: asyncio.run(main())
    except (KeyboardInterrupt, SystemExit): logger.info("程序退出。")
