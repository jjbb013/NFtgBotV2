import asyncio
import logging
import os
import re
import sys
import threading
import time
from collections import deque


class LogBufferHandler(logging.Handler):
    def __init__(self, max_lines=1000):
        super().__init__()
        self._buffer = deque(maxlen=max_lines)
        self._lock = threading.Lock()

    def emit(self, record):
        with self._lock:
            self._buffer.append(self.format(record))

    def get_lines(self, n=100):
        with self._lock:
            return list(self._buffer)[-n:]


log_buffer = LogBufferHandler(max_lines=1000)
log_buffer.setFormatter(
    logging.Formatter('%(asctime)s %(levelname)s %(message)s')
)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        log_buffer,
    ]
)
logger = logging.getLogger('tgBotV5')

SENSITIVE_PATTERNS = [
    (re.compile(r'(?<!\d)\+\d{7,15}(?!\d)'), '***PHONE***'),
    (re.compile(r'(?<![a-zA-Z])api[_-]?key\s*[:=]\s*["\']?[^"\'\s]+["\']?', re.IGNORECASE), 'api_key=***'),
    (re.compile(r'(?<![a-zA-Z])secret[_-]?key\s*[:=]\s*["\']?[^"\'\s]+["\']?', re.IGNORECASE), 'secret_key=***'),
    (re.compile(r'(?<![a-zA-Z])passphrase\s*[:=]\s*["\']?[^"\'\s]+["\']?', re.IGNORECASE), 'passphrase=***'),
    (re.compile(r'(?<![a-zA-Z])password\s*[:=]\s*["\']?[^"\'\s]+["\']?', re.IGNORECASE), 'password=***'),
    (re.compile(r'(?<![a-zA-Z])api[_-]?hash\s*[:=]\s*["\']?[a-zA-Z0-9]+["\']?', re.IGNORECASE), 'api_hash=***'),
    (re.compile(r'(?<![a-zA-Z])bark[_-]?key\s*[:=]\s*["\']?[^"\'\s]+["\']?', re.IGNORECASE), 'bark_key=***'),
    (re.compile(r'(?:verification|verify|auth|otp|telegram|login)\s+code\s*[:=]\s*["\']?\d{5,6}["\']?', re.IGNORECASE), 'code=***'),
]


def sanitize_log(line: str) -> str:
    for pattern, replacement in SENSITIVE_PATTERNS:
        line = pattern.sub(replacement, line)
    return line


from dotenv import load_dotenv

# Load environment-specific .env first, fall back to .env
if not load_dotenv('.env.local'):
    load_dotenv('.env')


def _int_env(name, default=None):
    val = os.getenv(name, default)
    if val is None:
        return None
    try:
        return int(val)
    except ValueError:
        logger.error(f'环境变量 {name} 必须是整数，当前值: {val!r}')
        sys.exit(1)


TG_API_ID = os.getenv('TG_API_ID')
TG_API_HASH = os.getenv('TG_API_HASH')
TG_LOG_GROUP_ID = os.getenv('TG_LOG_GROUP_ID')
TG_CHANNEL_IDS = os.getenv('TG_CHANNEL_IDS', '')
PATCH_MISSING_SIGNALS_INTERVAL = _int_env('PATCH_MISSING_SIGNALS_INTERVAL', '30')
HEALTH_CHECK_INTERVAL = _int_env('HEALTH_CHECK_INTERVAL', '300')

DASHBOARD_USERNAME = os.getenv('DASHBOARD_USERNAME')
DASHBOARD_PASSWORD = os.getenv('DASHBOARD_PASSWORD')
DASHBOARD_PORT = _int_env('DASHBOARD_PORT', '8000')

if not all([TG_API_ID, TG_API_HASH, TG_CHANNEL_IDS]):
    logger.error('关键环境变量 TG_API_ID, TG_API_HASH, TG_CHANNEL_IDS 未配置')
    sys.exit(1)

if not all([DASHBOARD_USERNAME, DASHBOARD_PASSWORD]):
    logger.error('Web Dashboard 环境变量 DASHBOARD_USERNAME, DASHBOARD_PASSWORD 未配置')
    sys.exit(1)

TG_API_ID = _int_env('TG_API_ID')
TG_LOG_GROUP_ID = _int_env('TG_LOG_GROUP_ID') if TG_LOG_GROUP_ID else None
CHANNEL_IDS = []
for cid in TG_CHANNEL_IDS.split(','):
    cid = cid.strip()
    if cid:
        try:
            CHANNEL_IDS.append(int(cid))
        except ValueError:
            logger.error(f'TG_CHANNEL_IDS 中的频道 ID 必须是整数: {cid!r}')
            sys.exit(1)

DATA_DIR = os.getenv('DATA_DIR', './data')
SESSION_DIR = os.getenv('SESSION_DIR', './data/sessions')
os.makedirs(SESSION_DIR, exist_ok=True)
LAST_SESSION_PATH_FILE = os.path.join(DATA_DIR, 'last_session_path.txt')


def get_session_file():
    if os.path.exists(LAST_SESSION_PATH_FILE):
        with open(LAST_SESSION_PATH_FILE, 'r', encoding='utf-8') as f:
            session_path = f.read().strip()
        if session_path and os.path.exists(session_path):
            logger.info(f'自动复用上次 session 文件: {session_path}')
            return session_path
        logger.warning('上次记录的 session 文件已不存在或无效，将重新选择')

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
        if choice.lower() != 'n':
            logger.info('输入无效，将新建登录')
        session_path = os.path.join(SESSION_DIR, f'session_{int(time.time())}.session')

    with open(LAST_SESSION_PATH_FILE, 'w', encoding='utf-8') as f:
        f.write(session_path)
    return session_path


def get_test_accounts():
    accounts = []
    for i in range(1, 6):
        prefix = f'OKX{i}_'
        if all(os.getenv(prefix + k) for k in ['API_KEY', 'SECRET_KEY', 'PASSPHRASE']):
            account_name = os.getenv(f'OKX{i}_ACCOUNT_NAME', f'OKX{i}').strip()
            accounts.append({
                'account_idx': i, 'account_name': account_name,
                'API_KEY': os.getenv(prefix + 'API_KEY'),
                'SECRET_KEY': os.getenv(prefix + 'SECRET_KEY'),
                'PASSPHRASE': os.getenv(prefix + 'PASSPHRASE'),
                'FLAG': os.getenv(prefix + 'FLAG', '0')
            })
    logger.info(f"共加载 {len(accounts)} 个有效OKX账户")
    return accounts


from datetime import datetime, timedelta, timezone
import okx.Account as Account
import okx.Trade as Trade
import okx.MarketData as MarketData

async def get_okx_connection_status(account):
    try:
        acc_api = Account.AccountAPI(
            account['API_KEY'], account['SECRET_KEY'], account['PASSPHRASE'], False, account['FLAG']
        )
        resp = await asyncio.to_thread(acc_api.get_account_balance)
        return resp.get('code') == '0'
    except Exception as e:
        logger.error(f"[{account['account_name']}] OKX 连接检查异常: {e}")
        return False


async def get_usdt_balance(account):
    try:
        acc_api = Account.AccountAPI(
            account['API_KEY'], account['SECRET_KEY'], account['PASSPHRASE'], False, account['FLAG']
        )
        resp = await asyncio.to_thread(acc_api.get_account_balance)
        if resp.get('code') == '0' and resp.get('data'):
            for detail in resp['data'][0].get('details', []):
                if detail.get('ccy') == 'USDT':
                    return float(detail.get('availEq', 0))
        logger.error(f"[{account['account_name']}] 获取余额失败: {resp.get('msg')}")
    except Exception as e:
        logger.error(f"[{account['account_name']}] 获取余额异常: {e}")
    return None


async def get_recent_pnl(account, days=7):
    try:
        acc_api = Account.AccountAPI(
            account['API_KEY'], account['SECRET_KEY'], account['PASSPHRASE'], False, account['FLAG']
        )
        start = datetime.now(timezone.utc) - timedelta(days=days)
        start_ms = int(start.timestamp() * 1000)

        total = 0.0
        before = None
        while True:
            kwargs = {'instType': 'SWAP', 'mgnMode': 'cross', 'limit': '100'}
            if before:
                kwargs['before'] = before
            resp = await asyncio.to_thread(acc_api.get_account_bills, **kwargs)
            if resp.get('code') != '0':
                logger.error(f"[{account['account_name']}] 获取账单失败: {resp.get('msg')}")
                return None

            data = resp.get('data', [])
            if not data:
                break

            reached_time_limit = False
            for item in data:
                ts = int(item.get('ts', 0))
                if ts < start_ms:
                    reached_time_limit = True
                    break
                pnl = item.get('pnl')
                if pnl is not None:
                    try:
                        total += float(pnl)
                    except (ValueError, TypeError):
                        continue

            if reached_time_limit:
                break

            before = data[-1].get('billId')
            if not before:
                break

        return round(total, 4)
    except Exception as e:
        logger.error(f"[{account['account_name']}] 获取账单异常: {e}")
    return None


async def get_recent_orders(account, limit=20):
    try:
        trade_api = Trade.TradeAPI(
            account['API_KEY'], account['SECRET_KEY'], account['PASSPHRASE'], False, account['FLAG']
        )
        resp = await asyncio.to_thread(
            trade_api.get_orders_history,
            instType='SWAP',
            limit=str(limit)
        )
        if resp.get('code') == '0':
            orders = []
            for item in resp.get('data', []):
                orders.append({
                    'instId': item.get('instId'),
                    'side': item.get('side'),
                    'posSide': item.get('posSide'),
                    'sz': item.get('sz'),
                    'avgPx': item.get('avgPx'),
                    'state': item.get('state'),
                    'cTime': item.get('cTime'),
                })
            return orders
        logger.error(f"[{account['account_name']}] 获取历史订单失败: {resp.get('msg')}")
    except Exception as e:
        logger.error(f"[{account['account_name']}] 获取历史订单异常: {e}")
    return []

