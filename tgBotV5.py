import asyncio
import logging
import os
import re
import subprocess
import sys
import threading
import time
import uvicorn
from collections import deque

import json
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from utils import get_shanghai_time, send_bark_notification, build_order_params, set_account_leverage
import okx.PublicData as PublicData


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
TELEGRAM_START_TIMEOUT = _int_env('TELEGRAM_START_TIMEOUT', '60')

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
os.makedirs(DATA_DIR, exist_ok=True)
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


def get_git_info():
    for cwd in ['/app', '.']:
        try:
            kwargs = {'cwd': cwd, 'text': True, 'timeout': 5}
            commit_hash = subprocess.check_output(
                ['git', 'rev-parse', '--short', 'HEAD'], **kwargs
            ).strip()
            commit_msg = subprocess.check_output(
                ['git', 'log', '-1', '--pretty=%s'], **kwargs
            ).strip()
            commit_time = subprocess.check_output(
                ['git', 'log', '-1', '--pretty=%ci'], **kwargs
            ).strip()
            return {'hash': commit_hash, 'message': commit_msg, 'time': commit_time}
        except (subprocess.CalledProcessError, FileNotFoundError,
                OSError, subprocess.TimeoutExpired) as e:
            logger.debug(f'无法从 {cwd} 获取 git 信息: {e}')
            continue
    logger.warning('获取 git 信息失败，未找到可用的 git 仓库')
    return {'hash': 'unknown', 'message': 'unknown', 'time': 'unknown'}


def get_active_version():
    for path in ['/app/supervisord.conf', './supervisord.conf']:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            match = re.search(
                r'^\s*command\s*=\s*(?:[/\w.-]+)?python3?(?:\.\d+)?\b'
                r'(?:\s+-\S+)*\s+\S*/?(tgBotV\d+\.py)',
                content,
                re.MULTILINE | re.IGNORECASE,
            )
            if match:
                return match.group(1)
        except (FileNotFoundError, PermissionError,
                IsADirectoryError, UnicodeDecodeError) as e:
            logger.debug(f'读取 supervisord.conf 失败: {path}: {e}')
            continue
    logger.warning('未在 supervisord.conf 中找到有效的 tgBotV 启动命令')
    return 'unknown'


from fastapi import FastAPI, Request, Depends, HTTPException, status, Query
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from pydantic import BaseModel
import secrets

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


class StaticAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path.startswith('/static/'):
            try:
                credentials = await security(request)
                correct_username = secrets.compare_digest(credentials.username, DASHBOARD_USERNAME)
                correct_password = secrets.compare_digest(credentials.password, DASHBOARD_PASSWORD)
                if not (correct_username and correct_password):
                    raise HTTPException(status_code=401)
            except HTTPException:
                return Response(
                    'Unauthorized',
                    status_code=401,
                    headers={'WWW-Authenticate': 'Basic'}
                )
        return await call_next(request)


security = HTTPBasic()
app.add_middleware(StaticAuthMiddleware)

templates = Jinja2Templates(directory='templates')
app.mount('/static', StaticFiles(directory='static'), name='static')


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, DASHBOARD_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, DASHBOARD_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Incorrect username or password',
            headers={'WWW-Authenticate': 'Basic'},
        )
    return credentials.username


@app.get('/health')
async def health():
    """Northflank / load balancer health check endpoint (no auth)."""
    return {'status': 'ok'}


@app.get('/', response_class=HTMLResponse)
async def dashboard(request: Request, username: str = Depends(verify_credentials)):
    return templates.TemplateResponse('dashboard.html', {
        'request': request,
    })


# Global Telegram client (initialized in main())
client = None


@app.get('/api/system/status')
async def system_status(username: str = Depends(verify_credentials)):
    active_version, git_info = await asyncio.gather(
        asyncio.to_thread(get_active_version),
        asyncio.to_thread(get_git_info),
    )
    return {
        'active_version': active_version,
        'git': git_info,
    }


@app.get('/api/telegram/status')
async def telegram_status(username: str = Depends(verify_credentials)):
    session_path = await asyncio.to_thread(get_session_file)
    status = {
        'session_path': session_path,
        'connected': False,
        'authorized': False,
        'channel_ids': CHANNEL_IDS,
        'me': None,
    }
    if client and client.is_connected():
        status['connected'] = True
        try:
            status['authorized'] = await client.is_user_authorized()
            if status['authorized']:
                me = await client.get_me()
                status['me'] = {
                    'id': me.id,
                    'first_name': me.first_name,
                    'last_name': me.last_name,
                    'username': me.username,
                }
        except Exception as e:
            logger.error(f'获取 Telegram 状态时出错: {e}')
    return status


TEST_ACCOUNTS = get_test_accounts()


@app.get('/api/okx/status')
async def okx_status(username: str = Depends(verify_credentials)):
    accounts = []
    for acc in TEST_ACCOUNTS:
        connected = await get_okx_connection_status(acc)
        balance = await get_usdt_balance(acc) if connected else None
        pnl = await get_recent_pnl(acc, days=7) if connected else None
        accounts.append({
            'name': acc['account_name'],
            'connected': connected,
            'balance': balance,
            'pnl': pnl,
        })
    return {'accounts': accounts}


@app.get('/api/okx/orders')
async def okx_orders(
    account: str = Query(default=None),
    account_idx: int = Query(default=None),
    username: str = Depends(verify_credentials)
):
    target = None
    if account_idx is not None:
        target = next((a for a in TEST_ACCOUNTS if a['account_idx'] == account_idx), None)
    elif account is not None:
        target = next((a for a in TEST_ACCOUNTS if a['account_name'] == account), None)
    if not target:
        raise HTTPException(status_code=404, detail='Account not found')
    orders = await get_recent_orders(target, limit=20)
    return {'orders': orders}


@app.get('/api/logs')
async def logs(username: str = Depends(verify_credentials)):
    raw_lines = log_buffer.get_lines(100)
    sanitized = [sanitize_log(line) for line in raw_lines]
    return {'lines': sanitized}


# --- Signal Extraction (ported from tgBotV4) ---
def extract_trade_info(message):
    logger.debug(f"正在从消息中提取交易信息: {message[:100]}...")
    close_keywords = ['空止盈', '空止损', '多止盈', '多止损', '平多', '平空', 'MA止损', 'MA 止损']
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
    close_type = None
    if any(kw in message for kw in ['执行交易:MA止损', 'MA止损', 'MA 止损']):
        close_type = 'both'
    elif any(kw in message for kw in ['空止盈', '空止损', '平空']):
        close_type = 'short'
    elif any(kw in message for kw in ['多止盈', '多止损', '平多']):
        close_type = 'long'
    else:
        return None, None

    symbol_pattern = r"策略当前交易对[:：]?(\w+USDT\.P)"
    symbol_match = re.search(symbol_pattern, message)
    if symbol_match:
        symbol = symbol_match.group(1).upper().replace('USDT.P', '').replace('USDT', '')
        logger.info(f"检测到平仓信号 ({close_type}): {symbol}")
        return close_type, symbol

    if close_type == 'both':
        trend_symbol_pattern = r"趋势策略-([A-Z]+)"
        trend_symbol_match = re.search(trend_symbol_pattern, message)
        if trend_symbol_match:
            symbol = trend_symbol_match.group(1).upper()
            logger.info(f"检测到平仓信号 ({close_type})，从趋势策略中提取到交易对: {symbol}")
            return close_type, symbol

        logger.warning(f"检测到平仓信号 ({close_type}) 但未能提取交易对。消息: {message}")
        return close_type, None

    logger.warning(f"检测到平仓信号 ({close_type}) 但未能提取交易对。消息: {message}")
    return close_type, None


# --- Processed Message IDs (ported from tgBotV4) ---
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
signal_lock = asyncio.Lock()
login_lock = asyncio.Lock()


# --- OKX Helpers (ported from tgBotV4, adapted for asyncio) ---
async def get_latest_market_price(symbol):
    try:
        api = MarketData.MarketAPI(flag='0', debug=False)
        response = await asyncio.to_thread(api.get_ticker, instId=f"{symbol.upper()}-USDT-SWAP")
        if response.get('code') == '0' and response.get('data'):
            return float(response['data'][0]['last'])
        logger.error(f"获取 {symbol} 价格失败: {response.get('msg')}")
    except Exception as e:
        logger.error(f"获取 {symbol} 价格异常: {e}")
    return None


async def convert_coin_to_contract_size(inst_id, px, sz, flag):
    """
    将币的数量转换为合约的张数。
    """
    try:
        publicDataAPI = PublicData.PublicAPI(flag=flag)
        result = await asyncio.to_thread(
            publicDataAPI.get_convert_contract_coin,
            instId=inst_id,
            px=str(px),
            sz=str(sz),
            type="1",
            unit="usds"
        )
        if result.get('code') == '0' and result.get('data'):
            converted_sz = float(result['data'][0]['sz'])
            logger.info(f"币张转换成功: {sz} USDT 价值 转换为 {converted_sz} 张合约 ({inst_id})")
            return converted_sz
        else:
            logger.error(f"币张转换失败: {result.get('msg', '未知错误')}")
            return None
    except Exception as e:
        logger.error(f"币张转换异常: {e}")
        return None


# --- Trading Functions (ported from tgBotV4, adapted for asyncio) ---
async def place_okx_order(account, action, symbol, size, price=None):
    try:
        api = Trade.TradeAPI(account['API_KEY'], account['SECRET_KEY'], account['PASSPHRASE'], False, account['FLAG'])
        if price is None:
            price = await get_latest_market_price(symbol)
        if not price:
            return {"success": False, "error_msg": "无法获取市场价格"}

        tp_ratio = float(os.getenv(f"OKX{account['account_idx']}_TP_RATIO", '0.01'))
        sl_ratio = float(os.getenv(f"OKX{account['account_idx']}_SL_RATIO", '0.027'))

        side, pos_side = ('buy', 'long') if action == '做多' else ('sell', 'short')
        tp_price = price * (1 + (tp_ratio if side == 'buy' else -tp_ratio))
        sl_price = price * (1 - (sl_ratio if side == 'buy' else -sl_ratio))

        params = build_order_params(
            f"{symbol}-USDT-SWAP", side, price, size, pos_side,
            round(tp_price, 4), round(sl_price, 4)
        )
        logger.info(f"下单参数: {json.dumps(params, indent=2)}")
        resp = await asyncio.to_thread(api.place_order, **params)
        logger.info(f"下单返回: {json.dumps(resp, indent=2)}")

        data = resp.get('data', [{}])[0]
        if resp.get('code') == '0' and data.get('sCode') == '0':
            leverage = int(os.getenv(f"OKX{account['account_idx']}_LEVERAGE", 10))
            return {
                "success": True,
                "market_price": price,
                "margin": round(price * size / leverage, 4),
                "take_profit": tp_price,
                "stop_loss": sl_price,
                "clOrdId": params['clOrdId'],
                "okx_resp": resp
            }
        else:
            return {"success": False, "error_msg": data.get('sMsg'), "okx_resp": resp}
    except Exception as e:
        logger.error(f"下单异常: {e}")
        return {"success": False, "error_msg": str(e)}


async def close_okx_position(account, symbol, close_type):
    try:
        acc_api = Account.AccountAPI(account['API_KEY'], account['SECRET_KEY'], account['PASSPHRASE'], False, account['FLAG'])
        trade_api = Trade.TradeAPI(account['API_KEY'], account['SECRET_KEY'], account['PASSPHRASE'], False, account['FLAG'])
        inst_id = f"{symbol.upper()}-USDT-SWAP"

        resp = await asyncio.to_thread(acc_api.get_positions, instId=inst_id)
        if resp.get('code') != '0':
            return {"success": False, "error_msg": "获取持仓失败"}

        results = []
        positions_to_close = []
        if close_type == 'both':
            positions_to_close = [p for p in resp.get('data', []) if float(p.get('pos', '0')) > 0]
        else:
            positions_to_close = [p for p in resp.get('data', []) if float(p.get('pos', '0')) > 0 and p.get('posSide') == close_type]

        if not positions_to_close:
            logger.info(f"[{account['account_name']}] 未找到 {symbol} 的 {close_type} 方向持仓可供平仓。")
            return {"success": True, "close_results": [], "message": "没有找到可平仓位"}

        total_upl = 0.0
        total_upl_ratio = 0.0
        valid_ratio_count = 0
        for p in positions_to_close:
            try:
                upl = float(p.get('upl', 0) or 0)
                total_upl += upl
                upl_ratio = p.get('uplRatio')
                if upl_ratio is not None:
                    ratio_val = float(upl_ratio)
                    if abs(ratio_val) < 1:
                        ratio_val = ratio_val * 100
                    total_upl_ratio += ratio_val
                    valid_ratio_count += 1
            except (ValueError, TypeError):
                continue
        pnl_pct = (total_upl_ratio / valid_ratio_count) if valid_ratio_count > 0 else None

        for pos in positions_to_close:
            pos_side_to_close = pos.get('posSide')
            side = 'sell' if pos_side_to_close == 'long' else 'buy'
            close_resp = await asyncio.to_thread(
                trade_api.place_order,
                instId=inst_id, tdMode='cross', side=side,
                posSide=pos_side_to_close, ordType='market', sz=pos['pos']
            )
            close_data = close_resp.get('data', [{}])[0]
            if close_resp.get('code') == '0' and close_data.get('sCode') == '0':
                results.append({
                    'pos_side': pos_side_to_close, 'size': pos['pos'],
                    'order_id': close_data.get('ordId')
                })
            else:
                logger.error(f"[{account['account_name']}] 平仓 {pos_side_to_close} {symbol} 失败: {close_data.get('sMsg')}")
                results.append({
                    'pos_side': pos_side_to_close, 'size': pos['pos'],
                    'error_msg': close_data.get('sMsg')
                })

        has_errors = any('error_msg' in res for res in results)
        if has_errors:
            error_messages = [f"{res['pos_side']}: {res['error_msg']}" for res in results if 'error_msg' in res]
            return {
                "success": False,
                "close_results": results,
                "okx_resp": resp,
                "total_upl": total_upl,
                "pnl_pct": pnl_pct,
                "error_msg": "; ".join(error_messages)
            }
        return {"success": True, "close_results": results, "okx_resp": resp, "total_upl": total_upl, "pnl_pct": pnl_pct}
    except Exception as e:
        logger.error(f"平仓异常: {e}")
        return {"success": False, "error_msg": str(e)}


# --- Signal Processors (ported from tgBotV4) ---
async def process_open_signal(action, symbol, msg_text):
    log_header = f"【补单】\n原始信息: {msg_text}" if "补单" in msg_text else f"【实时信号】\n原始信息: {msg_text}"

    price = await get_latest_market_price(symbol)
    if not price:
        logger.error(f"无法获取 {symbol} 的市场价格，跳过下单。")
        return

    for account in TEST_ACCOUNTS:
        balance = await get_usdt_balance(account)
        if balance is None:
            logger.error(f"无法获取账户 {account['account_name']} 的余额，跳过下单。")
            continue

        position_ratio = float(os.getenv(f"OKX{account['account_idx']}_POSITION_RATIO", "0.25"))
        margin = balance * position_ratio
        leverage = int(os.getenv(f"OKX{account['account_idx']}_LEVERAGE", "10"))

        order_value = margin * leverage
        inst_id = f"{symbol.upper()}-USDT-SWAP"
        converted_size = await convert_coin_to_contract_size(inst_id, price, order_value, account['FLAG'])

        if converted_size is None:
            logger.error(f"无法将币价值转换为合约张数，跳过下单。")
            continue

        size = converted_size

        order_details = (
            f"--- {account['account_name']} 下单计算 ---\n"
            f"当前余额: {balance:.4f} USDT\n"
            f"保证金数量: {margin:.4f} USDT\n"
            f"杠杆: {leverage}x\n"
            f"开仓价格: {price:.4f}\n"
            f"开仓方向: {action}\n"
            f"开仓张数: {size:.4f}\n"
            f"-------------------------"
        )
        logger.info(order_details)

        result = await place_okx_order(account, action, symbol, size, price)

        conversion_log = f"币张转换成功: {order_value:.4f} USDT 价值 转换为 {size:.4f} 张合约 ({inst_id})"
        full_log = f"{conversion_log}\n{order_details}"

        if TG_LOG_GROUP_ID:
            if len(full_log) > 4090:
                log_to_send = f"{full_log[:4000]}...\n(消息过长，已截断，请查看本地日志)"
                await client.send_message(TG_LOG_GROUP_ID, log_to_send)
            else:
                await client.send_message(TG_LOG_GROUP_ID, full_log)

        if result.get('success'):
            bark_title = f"✅ {account['account_name']} {action} {symbol}"
            bark_extra_info = (
                f"止盈价格: {result.get('take_profit', 0):.4f}\n"
                f"止损价格: {result.get('stop_loss', 0):.4f}\n"
                f"客户订单ID: {result.get('clOrdId', '')}\n"
                f"时间: {get_shanghai_time()}\n"
                f"服务器响应代码: {result.get('okx_resp', {}).get('code', '')}\n"
                f"服务器响应消息: {result.get('okx_resp', {}).get('msg', '')}"
            )
            bark_content = f"{full_log}\n{bark_extra_info}"
        else:
            bark_title = f"❌ {account['account_name']} {action} {symbol} 下单失败"
            bark_content = (
                f"{full_log}\n"
                f"错误信息: {result.get('error_msg', '未知错误')}\n"
                f"时间: {get_shanghai_time()}"
            )

        await asyncio.to_thread(send_bark_notification, bark_title, bark_content)

        original_signal_log = f"{log_header}\n信号判断: {action} {symbol} (账户: {account['account_name']})\n操作返回: {json.dumps(result, ensure_ascii=False, indent=2)}"
        logger.info(original_signal_log)
        if TG_LOG_GROUP_ID:
            if len(original_signal_log) > 4090:
                log_to_send = f"{original_signal_log[:4000]}...\n(消息过长，已截断，请查看本地日志)"
                await client.send_message(TG_LOG_GROUP_ID, log_to_send)
            else:
                await client.send_message(TG_LOG_GROUP_ID, original_signal_log)


def build_close_bark_content(close_type, symbol, account_name, close_results, okx_resp=None, error_msg=None, total_upl=None, pnl_pct=None):
    now = get_shanghai_time()
    lines = [
        f"账户: {account_name}",
        f"交易标的: {symbol}",
        f"信号类型: 平仓{close_type}",
        f"平仓结果: {len(close_results)} 个持仓",
        f"时间: {now}"
    ]
    if total_upl is not None:
        pnl_sign = "+" if total_upl >= 0 else ""
        if pnl_pct is not None:
            pct_sign = "+" if pnl_pct >= 0 else ""
            lines.append(f"盈亏: {pnl_sign}{total_upl:.4f} USDT ({pct_sign}{pnl_pct:.2f}%)")
        else:
            lines.append(f"盈亏: {pnl_sign}{total_upl:.4f} USDT")
    if close_results:
        for res in close_results:
            if 'order_id' in res:
                lines.append(f"- {res['pos_side']}: {res['size']} (订单ID: {res['order_id']})")
            else:
                lines.append(f"- {res['pos_side']}: {res['size']} (失败: {res.get('error_msg', '未知错误')})")
    if error_msg:
        lines.extend(["⚠️ 平仓失败 ⚠️", f"错误: {error_msg}"])
    if okx_resp:
        lines.extend([f"服务器响应代码: {okx_resp.get('code', '')}", f"服务器响应消息: {okx_resp.get('msg', '')}"])
    return "\n".join(lines)


async def process_close_signal(close_type, symbol, msg_text):
    log_header = f"【补单】\n原始信息: {msg_text}" if "补单" in msg_text else f"【实时信号】\n原始信息: {msg_text}"
    for account in TEST_ACCOUNTS:
        if symbol is None:
            error_msg = f"[{account['account_name']}] 平仓信号 ({close_type}) 未能提取交易对，跳过平仓。"
            logger.error(error_msg)
            if TG_LOG_GROUP_ID:
                await client.send_message(TG_LOG_GROUP_ID, f"{log_header}\n{error_msg}")
            await asyncio.to_thread(send_bark_notification, "⚠️ 平仓失败 ⚠️", error_msg)
            continue

        result = await close_okx_position(account, symbol, close_type)
        close_results = result.get('close_results', [])
        error_msg = result.get('error_msg')
        has_errors = any('error_msg' in res for res in close_results)
        icon = "❌ " if error_msg or has_errors else ""
        bark_title = f"{icon}Tg信号策略平仓-{symbol}"
        content = build_close_bark_content(
            close_type, symbol, account['account_name'],
            close_results, result.get('okx_resp'), error_msg,
            result.get('total_upl'), result.get('pnl_pct')
        )
        full_log = f"{log_header}\n信号判断: 平仓 {close_type} {symbol} (账户: {account['account_name']})\n操作返回: {json.dumps(result, ensure_ascii=False, indent=2)}"
        logger.info(full_log)
        if TG_LOG_GROUP_ID:
            if len(full_log) > 4090:
                log_to_send = f"{full_log[:4000]}...\n(消息过长，已截断，请查看本地日志)"
                await client.send_message(TG_LOG_GROUP_ID, log_to_send)
            else:
                await client.send_message(TG_LOG_GROUP_ID, full_log)
        await asyncio.to_thread(send_bark_notification, bark_title, content)


# --- Message Handler and Background Tasks (ported from tgBotV4) ---
async def handler(event):
    msg_text = event.message.text or ''

    async with signal_lock:
        if event.id in PROCESSED_MESSAGE_IDS.get(event.chat_id, set()):
            return
        PROCESSED_MESSAGE_IDS.setdefault(event.chat_id, set()).add(event.id)
        await asyncio.to_thread(save_processed_ids, PROCESSED_MESSAGE_IDS)

        if TG_LOG_GROUP_ID:
            forward_msg = f"【消息监听】频道:{event.chat_id}\n时间: {get_shanghai_time()}\n内容: {msg_text}"
            await client.send_message(TG_LOG_GROUP_ID, forward_msg)

        action, symbol = extract_trade_info(msg_text)
        if action and symbol:
            await process_open_signal(action, symbol, msg_text)
        close_type, close_symbol = extract_close_signal(msg_text)
        if close_type and close_symbol:
            await process_close_signal(close_type, close_symbol, msg_text)


async def health_check():
    while True:
        await asyncio.sleep(HEALTH_CHECK_INTERVAL)
        try:
            if not client.is_connected():
                raise ConnectionError("Client disconnected")
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
        try:
            for channel_id in CHANNEL_IDS:
                async for msg in client.iter_messages(channel_id, limit=20):
                    if not (msg and msg.text):
                        continue
                    async with signal_lock:
                        if msg.id in PROCESSED_MESSAGE_IDS.get(channel_id, set()):
                            continue
                        PROCESSED_MESSAGE_IDS.setdefault(channel_id, set()).add(msg.id)
                        await asyncio.to_thread(save_processed_ids, PROCESSED_MESSAGE_IDS)
                        action, symbol = extract_trade_info(msg.text)
                        if action and symbol:
                            await process_open_signal(action, symbol, f"补单: {msg.text}")
                        close_type, close_symbol = extract_close_signal(msg.text)
                        if close_type and close_symbol:
                            await process_close_signal(close_type, close_symbol, f"补单: {msg.text}")
        except Exception as e:
            logger.error(f"历史消息补单检查异常: {e}")


async def init_processed_ids():
    logger.info("正在初始化消息ID缓存...")
    async with signal_lock:
        for channel_id in CHANNEL_IDS:
            PROCESSED_MESSAGE_IDS.setdefault(channel_id, set())
            async for message in client.iter_messages(channel_id, limit=50):
                if message:
                    PROCESSED_MESSAGE_IDS[channel_id].add(message.id)
        await asyncio.to_thread(save_processed_ids, PROCESSED_MESSAGE_IDS)
    logger.info("消息ID缓存初始化完成。")


async def set_leverage_for_all_accounts():
    logger.info("正在为所有账户设置杠杆...")
    for account in TEST_ACCOUNTS:
        leverage = os.getenv(f"OKX{account['account_idx']}_LEVERAGE", "10")
        for symbol in ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "DOGE-USDT-SWAP", "SOL-USDT-SWAP"]:
            try:
                result = await asyncio.to_thread(
                    set_account_leverage,
                    account['API_KEY'], account['SECRET_KEY'], account['PASSPHRASE'],
                    account['FLAG'], symbol, leverage, "cross"
                )
                log_msg = f"【杠杆设置】{account['account_name']} {symbol}: {leverage}x - {result}"
                logger.info(log_msg)
                if TG_LOG_GROUP_ID:
                    await client.send_message(TG_LOG_GROUP_ID, log_msg)
            except Exception as e:
                logger.error(f"【杠杆设置异常】{account['account_name']} {symbol}: {e}")


async def send_startup_symbol_prices():
    logger.info("启动价格播报...")
    for symbol_id in ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "DOGE-USDT-SWAP", "SOL-USDT-SWAP"]:
        price = await get_latest_market_price(symbol_id.split('-')[0])
        if price and TG_LOG_GROUP_ID:
            await client.send_message(TG_LOG_GROUP_ID, f"【开盘价】{symbol_id}: {price}")



# --- Telegram Web Re-login Flow ---
login_state = {
    'phone': None,
    'phone_code_hash': None,
    'temp_client': None,
}

background_task_refs = []


async def stop_background_tasks():
    global background_task_refs
    for task in background_task_refs:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    background_task_refs = []
    logger.info('后台任务已停止')


async def start_background_tasks():
    global background_task_refs
    await stop_background_tasks()
    if client and client.is_connected():
        background_task_refs = [
            asyncio.create_task(check_and_patch_missing_signals()),
            asyncio.create_task(health_check()),
        ]
        logger.info('后台任务已启动')
    else:
        logger.warning('Telegram 客户端未连接，后台任务暂不启动')


async def replace_client(new_client):
    global client
    if client and client.is_connected():
        try:
            await client.disconnect()
        except Exception as e:
            logger.warning(f'断开旧 client 时出错: {e}')
    client = new_client
    client.on(events.NewMessage(chats=CHANNEL_IDS))(handler)


class PhoneRequest(BaseModel):
    phone: str


class CodeRequest(BaseModel):
    phone: str
    code: str
    phone_code_hash: str


class PasswordRequest(BaseModel):
    password: str


@app.post('/api/telegram/login/start')
async def telegram_login_start(
    req: PhoneRequest,
    username: str = Depends(verify_credentials)
):
    async with login_lock:
        return await _telegram_login_start(req)


async def _telegram_login_start(req: PhoneRequest):
    global login_state
    await stop_background_tasks()
    if client and client.is_connected():
        try:
            await client.disconnect()
        except Exception as e:
            logger.warning(f'断开当前 client 时出错: {e}')

    # 清理之前未完成的登录会话，避免临时客户端泄漏
    old_temp_client = login_state.get('temp_client')
    if old_temp_client and old_temp_client.is_connected():
        try:
            await old_temp_client.disconnect()
        except Exception as e:
            logger.warning(f'断开旧临时客户端时出错: {e}')
    login_state = {'phone': None, 'phone_code_hash': None, 'temp_client': None}

    session_path = await asyncio.to_thread(get_session_file)
    temp_client = TelegramClient(session_path, TG_API_ID, TG_API_HASH)
    try:
        await temp_client.connect()
        sent = await temp_client.send_code_request(req.phone)
        login_state = {
            'phone': req.phone,
            'phone_code_hash': sent.phone_code_hash,
            'temp_client': temp_client,
        }
        return {
            'success': True,
            'phone_code_hash': sent.phone_code_hash,
            'message': '验证码已发送',
        }
    except Exception as e:
        logger.error(f'发送验证码失败: {e}')
        if temp_client.is_connected():
            await temp_client.disconnect()
        login_state = {'phone': None, 'phone_code_hash': None, 'temp_client': None}
        await start_background_tasks()
        return {'success': False, 'error': str(e)}


@app.post('/api/telegram/login/verify')
async def telegram_login_verify(
    req: CodeRequest,
    username: str = Depends(verify_credentials)
):
    async with login_lock:
        return await _telegram_login_verify(req)


async def _telegram_login_verify(req: CodeRequest):
    global login_state
    temp_client = login_state.get('temp_client')
    if not temp_client:
        return {'success': False, 'error': '登录会话已过期，请重新开始'}
    try:
        await temp_client.sign_in(
            phone=req.phone,
            code=req.code,
            phone_code_hash=req.phone_code_hash,
        )
        await finalize_login(temp_client)
        return {'success': True, 'message': '登录成功'}
    except SessionPasswordNeededError:
        return {'success': True, 'need_password': True, 'message': '需要二步验证密码'}
    except Exception as e:
        logger.error(f'验证码登录失败: {e}')
        await cleanup_login(temp_client)
        return {'success': False, 'error': str(e)}


async def finalize_login(new_client):
    global login_state
    await replace_client(new_client)
    session_path = await asyncio.to_thread(get_session_file)
    try:
        await asyncio.to_thread(os.chmod, session_path, 0o600)
    except Exception as e:
        logger.warning(f'设置 session 文件权限失败: {e}')
    await start_background_tasks()
    login_state = {'phone': None, 'phone_code_hash': None, 'temp_client': None}


async def cleanup_login(temp_client):
    global login_state
    if temp_client and temp_client.is_connected():
        await temp_client.disconnect()
    login_state = {'phone': None, 'phone_code_hash': None, 'temp_client': None}
    await start_background_tasks()


@app.post('/api/telegram/login/password')
async def telegram_login_password(
    req: PasswordRequest,
    username: str = Depends(verify_credentials)
):
    async with login_lock:
        return await _telegram_login_password(req)


async def _telegram_login_password(req: PasswordRequest):
    global login_state
    temp_client = login_state.get('temp_client')
    if not temp_client:
        return {'success': False, 'error': '登录会话已过期，请重新开始'}
    try:
        await temp_client.check_password(req.password)
        await finalize_login(temp_client)
        return {'success': True, 'message': '登录成功'}
    except Exception as e:
        logger.error(f'二步验证失败: {e}')
        await cleanup_login(temp_client)
        return {'success': False, 'error': str(e)}


# --- Application Entry Point ---
async def start_telegram_client():
    """后台初始化 Telegram 客户端；失败时保留 Web Dashboard 可用。"""
    global client
    try:
        session_file = await asyncio.to_thread(get_session_file)
        client = TelegramClient(session_file, TG_API_ID, TG_API_HASH)
        await asyncio.wait_for(client.start(), timeout=TELEGRAM_START_TIMEOUT)
        logger.info(f'已登录 Telegram，监听频道: {CHANNEL_IDS}')

        # Register Telegram message handler
        client.on(events.NewMessage(chats=CHANNEL_IDS))(handler)

        await init_processed_ids()
        await set_leverage_for_all_accounts()
        await send_startup_symbol_prices()
        await start_background_tasks()

        logger.info('Telegram 客户端初始化完成')
    except Exception as e:
        logger.error(f'Telegram 客户端启动失败: {e}')
        logger.info('请通过 Web Dashboard 的重新登录功能完成 Telegram 登录')


async def main():
    config = uvicorn.Config(
        app,
        host='0.0.0.0',
        port=DASHBOARD_PORT,
        workers=1,
        loop='asyncio',
        log_config=None,
    )
    server = uvicorn.Server(config)

    # 先启动 Web Dashboard，让 Northflank 立刻有端口可探测；
    # Telegram 登录在后台进行，失败也不影响 Dashboard。
    telegram_task = asyncio.create_task(start_telegram_client())
    logger.info('Web Dashboard 将在 %s 端口启动', DASHBOARD_PORT)
    await server.serve()
    if not telegram_task.done():
        telegram_task.cancel()
        try:
            await telegram_task
        except asyncio.CancelledError:
            pass


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info('程序退出。')
