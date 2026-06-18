# tgBot Lite 重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `main` 分支基础上，把单文件 tgBotV4 重构为轻量化、模块化、MongoDB 持久化、带 Dashboard 的 Northflank 可部署版本。

**Architecture:** 用 FastAPI + Jinja2 提供轻量 Dashboard，Telethon 客户端作为 uvicorn 事件循环中的后台任务；核心交易逻辑拆到 `core/` 模块；MongoDB 存储 Telegram `StringSession` 和已处理消息 ID；删除历史文件和未使用依赖。

**Tech Stack:** Python 3.11, Telethon, FastAPI, Jinja2, uvicorn, pymongo, python-okx, requests, pytz, python-dotenv.

---

## 0. 文件结构（目标）

```text
.
├── config.py
├── db.py
├── main.py
├── requirements.txt
├── Dockerfile
├── README.md
├── project_log.md
├── AGENTS.md
├── core/
│   ├── __init__.py
│   ├── helpers.py
│   ├── account.py
│   ├── signals.py
│   └── processor.py
├── telegram_client.py
├── web/
│   ├── app.py
│   └── templates/
│       ├── base.html
│       ├── index.html
│       ├── orders.html
│       └── login.html
├── static/
│   └── style.css
├── tests/
│   ├── test_signals.py
│   └── test_helpers.py
├── generate_session.py          # 保留，可选
├── generate_session_v2.py       # 保留，可选
└── list_dialogs.py              # 保留，可选
```

---

## Task 1: 清理旧文件与未使用依赖

**目标：** 删除历史版本文件，调整 `requirements.txt` 和 `Dockerfile`。

**Files:**
- Delete: `tgBotV2.py`, `tgBotV3.py`, `tgBotV4.py`, `okx_account.py`, `utils.py`, `supervisord.conf`, `start.sh`
- Modify: `requirements.txt`, `Dockerfile`

---

### Step 1.1: 删除旧文件

Run:

```bash
cd /Users/will/Cursor\ Project/NFtgBotV2
git rm tgBotV2.py tgBotV3.py tgBotV4.py okx_account.py utils.py supervisord.conf start.sh
```

Expected: files removed from working tree and staged.

---

### Step 1.2: 重写 `requirements.txt`

Create/overwrite `requirements.txt`:

```text
telethon
requests
pytz
python-okx
python-dotenv
pymongo
fastapi
jinja2
uvicorn
python-multipart
```

---

### Step 1.3: 重写 `Dockerfile`

Create/overwrite `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "main.py"]
```

---

### Step 1.4: 提交

```bash
git add requirements.txt Dockerfile
git commit -m "chore: remove legacy files and switch to direct python main.py startup"
```

---

## Task 2: 配置模块 `config.py`

**目标：** 集中读取环境变量，提供账户列表。

**Files:**
- Create: `config.py`

---

### Step 2.1: 实现 `config.py`

```python
import os
import sys
from dotenv import load_dotenv

load_dotenv('.env')

TG_API_ID = os.getenv('TG_API_ID')
TG_API_HASH = os.getenv('TG_API_HASH')
TG_CHANNEL_IDS = os.getenv('TG_CHANNEL_IDS', '')
TG_LOG_GROUP_ID = os.getenv('TG_LOG_GROUP_ID') or None

PATCH_MISSING_SIGNALS_INTERVAL = int(os.getenv('PATCH_MISSING_SIGNALS_INTERVAL', '30'))
HEALTH_CHECK_INTERVAL = int(os.getenv('HEALTH_CHECK_INTERVAL', '300'))
LOG_BUFFER_SIZE = int(os.getenv('LOG_BUFFER_SIZE', '500'))

DASHBOARD_PORT = int(os.getenv('DASHBOARD_PORT', '8000'))
DASHBOARD_USERNAME = os.getenv('DASHBOARD_USERNAME', 'admin')
DASHBOARD_PASSWORD = os.getenv('DASHBOARD_PASSWORD')
MONGODB_URI = os.getenv('MONGODB_URI')

_MISSING = []
if not TG_API_ID or not TG_API_HASH or not TG_CHANNEL_IDS:
    _MISSING.append('TG_API_ID, TG_API_HASH, TG_CHANNEL_IDS')
if not MONGODB_URI:
    _MISSING.append('MONGODB_URI')

if _MISSING:
    print(f"[FATAL] 缺少必需环境变量: {', '.join(_MISSING)}", file=sys.stderr)
    sys.exit(1)

TG_API_ID = int(TG_API_ID)
TG_LOG_GROUP_ID = int(TG_LOG_GROUP_ID) if TG_LOG_GROUP_ID else None
CHANNEL_IDS = [int(cid.strip()) for cid in TG_CHANNEL_IDS.split(',') if cid.strip()]


def get_accounts():
    accounts = []
    for i in range(1, 6):
        prefix = f'OKX{i}_'
        if all(os.getenv(prefix + k) for k in ['API_KEY', 'SECRET_KEY', 'PASSPHRASE']):
            accounts.append({
                'account_idx': i,
                'account_name': os.getenv(prefix + 'ACCOUNT_NAME', f'OKX{i}'),
                'API_KEY': os.getenv(prefix + 'API_KEY'),
                'SECRET_KEY': os.getenv(prefix + 'SECRET_KEY'),
                'PASSPHRASE': os.getenv(prefix + 'PASSPHRASE'),
                'FLAG': os.getenv(prefix + 'FLAG', '0'),
                'LEVERAGE': int(os.getenv(prefix + 'LEVERAGE', '10')),
                'POSITION_RATIO': float(os.getenv(prefix + 'POSITION_RATIO', '0.25')),
                'TP_RATIO': float(os.getenv(prefix + 'TP_RATIO', '0.01')),
                'SL_RATIO': float(os.getenv(prefix + 'SL_RATIO', '0.027')),
            })
    return accounts
```

---

### Step 2.2: 提交

```bash
git add config.py
git commit -m "feat(config): centralize env loading and account parsing"
```

---

## Task 3: MongoDB 持久化模块 `db.py`

**目标：** 使用 MongoDB 存储 session string 和已处理消息 ID。

**Files:**
- Create: `db.py`

---

### Step 3.1: 实现 `db.py`

```python
import os
import sys
from pymongo import MongoClient
from config import MONGODB_URI

_STATE_ID = 'singleton'
_MAX_IDS_PER_CHANNEL = 1000

try:
    _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    _client.admin.command('ping')
    _db = _client['tgbot_lite']
    _state = _db['state']
except Exception as e:
    print(f"[FATAL] 无法连接 MongoDB: {e}", file=sys.stderr)
    sys.exit(1)


def load_session_string():
    doc = _state.find_one({'_id': _STATE_ID})
    return doc.get('session_string') if doc else None


def save_session_string(session_string):
    _state.update_one(
        {'_id': _STATE_ID},
        {'$set': {'session_string': session_string}},
        upsert=True,
    )


def load_processed_ids():
    doc = _state.find_one({'_id': _STATE_ID})
    raw = doc.get('processed_message_ids', {}) if doc else {}
    return {int(k): set(v[-_MAX_IDS_PER_CHANNEL:]) for k, v in raw.items()}


def save_processed_ids(ids):
    data = {str(k): list(v)[-_MAX_IDS_PER_CHANNEL:] for k, v in ids.items()}
    _state.update_one(
        {'_id': _STATE_ID},
        {'$set': {'processed_message_ids': data}},
        upsert=True,
    )
```

---

### Step 3.2: 提交

```bash
git add db.py
git commit -m "feat(db): add MongoDB persistence for session string and processed IDs"
```

---

## Task 4: 工具函数模块 `core/helpers.py`

**目标：** 提取时间、订单 ID、下单参数、Bark 通知等通用函数。

**Files:**
- Create: `core/__init__.py`, `core/helpers.py`

---

### Step 4.1: 创建空 `core/__init__.py`

```bash
touch core/__init__.py
```

---

### Step 4.2: 实现 `core/helpers.py`

```python
import os
import random
import string
import time
import urllib.parse
from datetime import datetime, timezone, timedelta

import requests


def get_shanghai_time(fmt="%Y-%m-%d %H:%M:%S"):
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime(fmt)


def generate_clord_id(prefix="ORD"):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    rand = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
    return f"{prefix}{timestamp}{rand}"[:32]


def build_order_params(inst_id, side, entry_price, size, pos_side, take_profit, stop_loss, prefix="ORD"):
    cl_ord_id = generate_clord_id(prefix)
    attach_algo_ord = {
        "attachAlgoClOrdId": generate_clord_id(prefix),
        "tpTriggerPx": str(take_profit),
        "tpOrdPx": "-1",
        "tpOrdKind": "condition",
        "slTriggerPx": str(stop_loss),
        "slOrdPx": "-1",
        "tpTriggerPxType": "last",
        "slTriggerPxType": "last",
    }
    return {
        "instId": inst_id,
        "tdMode": "cross",
        "side": side,
        "ordType": "market",
        "sz": str(size),
        "clOrdId": cl_ord_id,
        "posSide": pos_side,
        "attachAlgoOrds": [attach_algo_ord],
    }


def send_bark_notification(title, content, group="NF-TgBotV2"):
    bark_key = os.getenv("BARK_KEY")
    if not bark_key:
        return
    base_url = bark_key if bark_key.startswith("http") else f"https://api.day.app/{bark_key}"
    try:
        resp = requests.post(
            base_url,
            json={"title": title, "body": content, "group": group},
            timeout=10,
        )
        if resp.status_code == 200:
            return
    except Exception as e:
        print(f"[Bark通知] POST失败: {e}")
    try:
        requests.get(
            f"{base_url}/{urllib.parse.quote(title)}/{urllib.parse.quote(content)}?group={group}",
            timeout=10,
        )
    except Exception as e:
        print(f"[Bark通知] GET失败: {e}")
```

---

### Step 4.3: 提交

```bash
git add core/__init__.py core/helpers.py
git commit -m "feat(core/helpers): add shared helpers migrated from utils.py"
```

---

## Task 5: OKX 账户模块 `core/account.py`

**目标：** 封装每个 OKX 账户的行情、余额、下单、平仓、订单查询、杠杆设置。

**Files:**
- Create: `core/account.py`

---

### Step 5.1: 实现 `core/account.py`

```python
import json
import logging

import okx.Account as Account
import okx.MarketData as MarketData
import okx.Trade as Trade

from core.helpers import generate_clord_id, get_shanghai_time

logger = logging.getLogger(__name__)


class OKXAccount:
    def __init__(self, config):
        self.cfg = config
        self.idx = config['account_idx']
        self.name = config['account_name']
        self.flag = config['FLAG']
        key = config['API_KEY']
        secret = config['SECRET_KEY']
        passphrase = config['PASSPHRASE']
        self.trade_api = Trade.TradeAPI(key, secret, passphrase, False, self.flag)
        self.account_api = Account.AccountAPI(key, secret, passphrase, False, self.flag)
        self.market_api = MarketData.MarketAPI(flag=self.flag, debug=False)

    def _inst_id(self, symbol):
        return f"{symbol.upper()}-USDT-SWAP"

    def get_price(self, symbol):
        try:
            inst_id = self._inst_id(symbol)
            resp = self.market_api.get_ticker(instId=inst_id)
            if resp.get('code') == '0' and resp.get('data'):
                return float(resp['data'][0]['last'])
            logger.error(f"[{self.name}] 获取 {symbol} 价格失败: {resp.get('msg')}")
        except Exception as e:
            logger.error(f"[{self.name}] 获取 {symbol} 价格异常: {e}")
        return None

    def get_balance(self):
        try:
            resp = self.account_api.get_account_balance()
            if resp.get('code') == '0':
                for detail in resp['data'][0].get('details', []):
                    if detail.get('ccy') == 'USDT':
                        return float(detail.get('availEq', 0))
            logger.error(f"[{self.name}] 获取余额失败: {resp.get('msg')}")
        except Exception as e:
            logger.error(f"[{self.name}] 获取余额异常: {e}")
        return None

    def place_order(self, action, symbol, size):
        try:
            price = self.get_price(symbol)
            if not price:
                return {"success": False, "error_msg": "无法获取市场价格"}

            tp_ratio = self.cfg['TP_RATIO']
            sl_ratio = self.cfg['SL_RATIO']
            leverage = self.cfg['LEVERAGE']

            side, pos_side = ('buy', 'long') if action == '做多' else ('sell', 'short')
            tp_price = price * (1 + (tp_ratio if side == 'buy' else -tp_ratio))
            sl_price = price * (1 - (sl_ratio if side == 'buy' else -sl_ratio))
            tp_price = round(tp_price, 4)
            sl_price = round(sl_price, 4)

            params = build_order_params(
                self._inst_id(symbol), side, price, size, pos_side, tp_price, sl_price
            )
            logger.info(f"[{self.name}] 下单参数: {json.dumps(params, ensure_ascii=False)}")
            resp = self.trade_api.place_order(**params)
            logger.info(f"[{self.name}] 下单返回: {json.dumps(resp, ensure_ascii=False)}")

            if resp.get('code') == '0' and resp.get('data') and resp['data'][0].get('sCode') == '0':
                margin = round(price * size / leverage, 4)
                return {
                    "success": True,
                    "market_price": price,
                    "margin": margin,
                    "take_profit": tp_price,
                    "stop_loss": sl_price,
                    "clOrdId": params['clOrdId'],
                    "okx_resp": resp,
                }
            return {"success": False, "error_msg": resp['data'][0].get('sMsg', '未知错误'), "okx_resp": resp}
        except Exception as e:
            logger.error(f"[{self.name}] 下单异常: {e}")
            return {"success": False, "error_msg": str(e)}

    def close_positions(self, symbol, close_type):
        try:
            inst_id = self._inst_id(symbol)
            resp = self.account_api.get_positions(instId=inst_id)
            if resp.get('code') != '0':
                return {"success": False, "error_msg": f"获取持仓失败: {resp.get('msg')}"}

            positions = []
            if close_type == 'both':
                positions = [p for p in resp.get('data', []) if float(p.get('pos', '0')) > 0]
            else:
                positions = [
                    p for p in resp.get('data', [])
                    if float(p.get('pos', '0')) > 0 and p.get('posSide') == close_type
                ]

            if not positions:
                return {"success": True, "close_results": [], "message": "没有可平仓位"}

            results = []
            for pos in positions:
                pos_side = pos.get('posSide')
                side = 'sell' if pos_side == 'long' else 'buy'
                close_resp = self.trade_api.place_order(
                    instId=inst_id,
                    tdMode='cross',
                    side=side,
                    posSide=pos_side,
                    ordType='market',
                    sz=pos['pos'],
                )
                if close_resp.get('code') == '0' and close_resp['data'][0].get('sCode') == '0':
                    results.append({
                        'pos_side': pos_side,
                        'size': pos['pos'],
                        'order_id': close_resp['data'][0]['ordId'],
                    })
                else:
                    results.append({
                        'pos_side': pos_side,
                        'size': pos['pos'],
                        'error_msg': close_resp['data'][0].get('sMsg', '未知错误'),
                    })
            return {"success": True, "close_results": results, "okx_resp": resp}
        except Exception as e:
            logger.error(f"[{self.name}] 平仓异常: {e}")
            return {"success": False, "error_msg": str(e)}

    def get_orders(self, symbol, limit=10):
        try:
            inst_id = self._inst_id(symbol)
            resp = self.trade_api.get_orders_history(
                instType='SWAP',
                instId=inst_id,
                limit=str(limit),
            )
            if resp.get('code') == '0':
                return resp.get('data', [])
            logger.error(f"[{self.name}] 获取订单历史失败: {resp.get('msg')}")
        except Exception as e:
            logger.error(f"[{self.name}] 获取订单历史异常: {e}")
        return []

    def set_leverage(self, symbol, leverage):
        try:
            inst_id = self._inst_id(symbol)
            resp = self.account_api.set_leverage(
                instId=inst_id,
                lever=str(leverage),
                mgnMode='cross',
            )
            msg = resp.get('msg', '成功') if resp.get('code') == '0' else str(resp)
            log = f"[{self.name}] {inst_id} 杠杆设置为 {leverage}x (cross) - {msg}"
            logger.info(log)
            return log
        except Exception as e:
            logger.error(f"[{self.name}] {symbol} 杠杆设置异常: {e}")
            return f"[{self.name}] {symbol} 杠杆设置异常: {e}"
```

---

### Step 5.2: 提交

```bash
git add core/account.py
git commit -m "feat(core/account): add OKXAccount wrapper for market/order/account APIs"
```

---

## Task 6: 信号解析模块 `core/signals.py`

**目标：** 迁移 tgBotV4 的正则解析逻辑，并补充单元测试。

**Files:**
- Create: `core/signals.py`, `tests/test_signals.py`

---

### Step 6.1: 实现 `core/signals.py`

```python
import re
import logging

logger = logging.getLogger(__name__)

CLOSE_KEYWORDS_BOTH = ['执行交易:MA止损', 'MA止损', 'MA 止损']
CLOSE_KEYWORDS_SHORT = ['空止盈', '空止损', '平空']
CLOSE_KEYWORDS_LONG = ['多止盈', '多止损', '平多']


def extract_trade_info(message):
    if any(kw in message for kw in CLOSE_KEYWORDS_BOTH + CLOSE_KEYWORDS_SHORT + CLOSE_KEYWORDS_LONG):
        return None, None

    action_pattern = r"执行交易[:：]?(.+?)(?= \d+\.\d+\w+)"
    action_match = re.search(action_pattern, message)
    symbol_pattern = r"策略当前交易对[:：]?(\w+USDT\.P)"
    symbol_match = re.search(symbol_pattern, message)

    if action_match and symbol_match:
        action_text = action_match.group(1).strip()
        symbol = symbol_match.group(1).replace('USDT.P', '')
        action = '做多' if '做多' in action_text or '买入' in action_text else '做空'
        return action, symbol

    patterns = {
        '做多': [
            r'做多\s*([A-Z]+)', r'([A-Z]+)\s*做多',
            r'买入\s*([A-Z]+)', r'([A-Z]+)\s*买入',
            r'LONG\s*([A-Z]+)', r'([A-Z]+)\s*LONG',
        ],
        '做空': [
            r'做空\s*([A-Z]+)', r'([A-Z]+)\s*做空',
            r'卖出\s*([A-Z]+)', r'([A-Z]+)\s*卖出',
            r'SHORT\s*([A-Z]+)', r'([A-Z]+)\s*SHORT',
        ],
    }
    for action, pattern_list in patterns.items():
        for pattern in pattern_list:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return action, match.group(1).upper()
    return None, None


def extract_close_signal(message):
    close_type = None
    if any(kw in message for kw in CLOSE_KEYWORDS_BOTH):
        close_type = 'both'
    elif any(kw in message for kw in CLOSE_KEYWORDS_SHORT):
        close_type = 'short'
    elif any(kw in message for kw in CLOSE_KEYWORDS_LONG):
        close_type = 'long'
    else:
        return None, None

    symbol_pattern = r"策略当前交易对[:：]?(\w+USDT\.P)"
    symbol_match = re.search(symbol_pattern, message)
    if symbol_match:
        symbol = symbol_match.group(1).upper().replace('USDT.P', '').replace('USDT', '')
        return close_type, symbol

    if close_type == 'both':
        trend_match = re.search(r"趋势策略-([A-Z]+)", message)
        if trend_match:
            return close_type, trend_match.group(1).upper()

    logger.warning(f"检测到平仓信号 ({close_type}) 但未能提取交易对。消息: {message}")
    return close_type, None
```

---

### Step 6.2: 实现 `tests/test_signals.py`

```python
import pytest
from core.signals import extract_trade_info, extract_close_signal


def test_extract_long_btc():
    action, symbol = extract_trade_info("做多 BTC")
    assert action == '做多'
    assert symbol == 'BTC'


def test_extract_short_eth():
    action, symbol = extract_trade_info("ETH 做空")
    assert action == '做空'
    assert symbol == 'ETH'


def test_extract_formatted_signal():
    msg = "执行交易:做多 123.45USDT 策略当前交易对:BTCUSDT.P"
    action, symbol = extract_trade_info(msg)
    assert action == '做多'
    assert symbol == 'BTC'


def test_extract_long_ignores_close():
    assert extract_trade_info("平空 BTC") == (None, None)


def test_close_long():
    close_type, symbol = extract_close_signal("多止盈 BTCUSDT.P")
    assert close_type == 'long'
    assert symbol == 'BTC'


def test_close_both_ma():
    close_type, symbol = extract_close_signal("趋势策略-ETH MA止损")
    assert close_type == 'both'
    assert symbol == 'ETH'
```

---

### Step 6.3: 运行测试

```bash
cd /Users/will/Cursor\ Project/NFtgBotV2
python -m pytest tests/test_signals.py -v
```

Expected: 6 tests pass.

---

### Step 6.4: 提交

```bash
git add core/signals.py tests/test_signals.py
git commit -m "feat(core/signals): migrate signal parsing with unit tests"
```

---

## Task 7: 信号处理模块 `core/processor.py`

**目标：** 实现开仓/平仓处理，使用内存日志缓冲，减少 Telegram 噪音。

**Files:**
- Create: `core/processor.py`
- Modify: `core/helpers.py` (ensure `build_order_params` import if needed)

---

### Step 7.1: 实现 `core/processor.py`

```python
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

# Global references set by telegram_client.py after startup
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

    # Use first account to fetch reference price once
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
```

---

### Step 7.2: 提交

```bash
git add core/processor.py
git commit -m "feat(core/processor): implement open/close signal processing with in-memory log buffer"
```

---

## Task 8: Telegram 客户端模块 `telegram_client.py`

**目标：** 使用 `StringSession` + MongoDB，注册消息处理器，启动补单/健康检查，提供网页登录接口。

**Files:**
- Create: `telegram_client.py`

---

### Step 8.1: 实现 `telegram_client.py`

```python
import asyncio
import json
import logging
import sys

from telethon import TelegramClient, events
from telethon.sessions import StringSession

import config
import db
from core import processor, signals
from core.account import OKXAccount
from core.helpers import get_shanghai_time

logger = logging.getLogger(__name__)

client: TelegramClient | None = None
_pending_login = {}
_login_lock = asyncio.Lock()

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

    logger.info(f"已登录 Telegram，监听频道: {config.CHANNEL_IDS}")
    await init_processed_ids()
    await set_leverage_for_all()
    await send_startup_prices()

    asyncio.create_task(check_and_patch_missing_signals())
    asyncio.create_task(health_check())

    await client.run_until_disconnected()


async def start_login(phone):
    global client
    async with _login_lock:
        if client is None:
            client = TelegramClient(
                StringSession(),
                config.TG_API_ID,
                config.TG_API_HASH,
            )
        try:
            result = await client.send_code_request(phone)
            _pending_login['phone'] = phone
            _pending_login['phone_code_hash'] = result.phone_code_hash
            return {'success': True, 'phone_code_hash': result.phone_code_hash}
        except Exception as e:
            logger.error(f"发送验证码失败: {e}")
            return {'success': False, 'error': str(e)}


async def confirm_login(phone, code):
    async with _login_lock:
        if _pending_login.get('phone') != phone:
            return {'success': False, 'error': '请先发送验证码'}
        try:
            await client.sign_in(phone, code, phone_code_hash=_pending_login['phone_code_hash'])
            session_str = client.session.save()
            db.save_session_string(session_str)
            _pending_login.clear()
            processor.set_telegram_client(client)
            return {'success': True, 'session_saved': True}
        except Exception as e:
            logger.error(f"登录确认失败: {e}")
            return {'success': False, 'error': str(e)}


def is_connected():
    return client.is_connected() if client else False
```

---

### Step 8.2: 提交

```bash
git add telegram_client.py
git commit -m "feat(telegram_client): StringSession + MongoDB, handlers, health/patch tasks, web login"
```

---

## Task 9: Dashboard 与 Web 模块

**目标：** 创建 FastAPI Dashboard、模板、静态资源和认证。

**Files:**
- Create: `web/app.py`, `web/templates/base.html`, `web/templates/index.html`, `web/templates/orders.html`, `web/templates/login.html`, `static/style.css`

---

### Step 9.1: 实现 `web/app.py`

```python
import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config
import telegram_client
from core import processor
from core.account import OKXAccount

security = HTTPBasic(auto_error=False)


def verify(credentials: HTTPBasicCredentials | None):
    if not credentials:
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
    correct = secrets.compare_digest(credentials.username, config.DASHBOARD_USERNAME) and \
              secrets.compare_digest(credentials.password, config.DASHBOARD_PASSWORD)
    if not correct:
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})


async def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    verify(credentials)
    return credentials.username


@asynccontextmanager
async def lifespan(app: FastAPI):
    telegram_task = asyncio.create_task(telegram_client.start_client())
    app.state.startup_time = datetime.utcnow().isoformat()
    app.state.telegram_task = telegram_task
    yield
    telegram_task.cancel()
    try:
        await telegram_task
    except asyncio.CancelledError:
        pass
    if telegram_client.client:
        await telegram_client.client.disconnect()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="web/templates")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "telegram_connected": telegram_client.is_connected(),
        "startup_time": getattr(app.state, 'startup_time', None),
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user: str = Depends(get_current_user)):
    accounts = telegram_client.accounts
    return templates.TemplateResponse("index.html", {
        "request": request,
        "accounts": [a.name for a in accounts],
        "telegram_connected": telegram_client.is_connected(),
        "startup_time": getattr(app.state, 'startup_time', None),
        "logs": list(processor.log_buffer)[-50:],
    })


@app.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request, user: str = Depends(get_current_user)):
    return templates.TemplateResponse("orders.html", {"request": request})


@app.get("/api/orders")
async def api_orders(account_idx: int = Query(1), symbol: str = Query("BTC"), user: str = Depends(get_current_user)):
    account = next((a for a in telegram_client.accounts if a.idx == account_idx), None)
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    data = account.get_orders(symbol)
    return {"account": account.name, "symbol": symbol, "orders": data}


@app.get("/logs")
async def logs(user: str = Depends(get_current_user)):
    return {"logs": list(processor.log_buffer)}


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/api/login/start")
async def api_login_start(payload: dict):
    phone = payload.get("phone")
    if not phone:
        raise HTTPException(status_code=400, detail="phone 必填")
    result = await telegram_client.start_login(phone)
    return JSONResponse(result)


@app.post("/api/login/confirm")
async def api_login_confirm(payload: dict):
    phone = payload.get("phone")
    code = payload.get("code")
    if not phone or not code:
        raise HTTPException(status_code=400, detail="phone 和 code 必填")
    result = await telegram_client.confirm_login(phone, code)
    return JSONResponse(result)
```

---

### Step 9.2: 创建模板文件

`web/templates/base.html`:

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}TgBot Lite{% endblock %}</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <nav>
        <a href="/">状态</a>
        <a href="/orders">订单</a>
        <a href="/logs">日志</a>
        <a href="/login">登录 Telegram</a>
    </nav>
    <main>{% block content %}{% endblock %}</main>
</body>
</html>
```

`web/templates/index.html`:

```html
{% extends "base.html" %}
{% block title %}状态 | TgBot Lite{% endblock %}
{% block content %}
<h1>运行状态</h1>
<p>Telegram 连接: {{ "✅ 已连接" if telegram_connected else "❌ 未连接" }}</p>
<p>启动时间: {{ startup_time }}</p>
<p>账户: {{ ", ".join(accounts) }}</p>
<h2>最近日志</h2>
<pre>{% for line in logs %}{{ line }}
{% endfor %}</pre>
{% endblock %}
```

`web/templates/orders.html`:

```html
{% extends "base.html" %}
{% block title %}订单 | TgBot Lite{% endblock %}
{% block content %}
<h1>最近订单</h1>
<p>选择账户和标的后实时查询 OKX。</p>
<div id="orders">加载中...</div>
<script>
async function load() {
    const params = new URLSearchParams({account_idx: '1', symbol: 'BTC'});
    const res = await fetch('/api/orders?' + params);
    const data = await res.json();
    document.getElementById('orders').innerText = JSON.stringify(data, null, 2);
}
load();
</script>
{% endblock %}
```

`web/templates/login.html`:

```html
{% extends "base.html" %}
{% block title %}登录 Telegram | TgBot Lite{% endblock %}
{% block content %}
<h1>Telegram 登录</h1>
<div>
    <input id="phone" placeholder="手机号 (+86138...)" type="text">
    <button onclick="startLogin()">发送验证码</button>
</div>
<div>
    <input id="code" placeholder="验证码" type="text">
    <button onclick="confirmLogin()">确认登录</button>
</div>
<pre id="result"></pre>
<script>
let phoneCodeHash = '';
async function startLogin() {
    const phone = document.getElementById('phone').value;
    const res = await fetch('/api/login/start', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({phone}),
    });
    const data = await res.json();
    phoneCodeHash = data.phone_code_hash || '';
    document.getElementById('result').innerText = JSON.stringify(data, null, 2);
}
async function confirmLogin() {
    const phone = document.getElementById('phone').value;
    const code = document.getElementById('code').value;
    const res = await fetch('/api/login/confirm', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({phone, code}),
    });
    const data = await res.json();
    document.getElementById('result').innerText = JSON.stringify(data, null, 2);
}
</script>
{% endblock %}
```

---

### Step 9.3: 创建 `static/style.css`

```css
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0f172a;
    color: #e2e8f0;
    margin: 0;
    padding: 0;
}
nav {
    background: #1e293b;
    padding: 1rem;
    display: flex;
    gap: 1rem;
}
nav a {
    color: #93c5fd;
    text-decoration: none;
}
main {
    padding: 1.5rem;
    max-width: 900px;
    margin: 0 auto;
}
pre {
    background: #1e293b;
    padding: 1rem;
    border-radius: 0.5rem;
    overflow-x: auto;
}
input, button {
    padding: 0.5rem;
    margin: 0.25rem 0;
}
```

---

### Step 9.4: 提交

```bash
git add web/app.py web/templates static/style.css
git commit -m "feat(web): add FastAPI dashboard, templates, login wizard and basic auth"
```

---

## Task 10: 入口程序 `main.py`

**目标：** 启动 uvicorn，加载 Web app。

**Files:**
- Create: `main.py`

---

### Step 10.1: 实现 `main.py`

```python
import uvicorn
import config

if __name__ == '__main__':
    uvicorn.run(
        'web.app:app',
        host='0.0.0.0',
        port=config.DASHBOARD_PORT,
        workers=1,
        loop='asyncio',
        log_config=None,
    )
```

---

### Step 10.2: 提交

```bash
git add main.py
git commit -m "feat(main): add uvicorn entrypoint"
```

---

## Task 11: 单元测试与本地验证

**目标：** 补充 `tests/test_helpers.py`，运行测试，本地启动验证 `/health`。

**Files:**
- Create: `tests/test_helpers.py`

---

### Step 11.1: 实现 `tests/test_helpers.py`

```python
import re
from core.helpers import generate_clord_id, get_shanghai_time, build_order_params


def test_generate_clord_id_format():
    cid = generate_clord_id("ORD")
    assert cid.startswith("ORD")
    assert len(cid) <= 32


def test_get_shanghai_time_format():
    ts = get_shanghai_time()
    assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", ts)


def test_build_order_params():
    params = build_order_params("BTC-USDT-SWAP", "buy", 70000.0, 1.5, "long", 71000.0, 69000.0)
    assert params['instId'] == "BTC-USDT-SWAP"
    assert params['side'] == "buy"
    assert params['posSide'] == "long"
    assert len(params['attachAlgoOrds']) == 1
```

---

### Step 11.2: 运行全部测试

```bash
cd /Users/will/Cursor\ Project/NFtgBotV2
python -m pytest tests/ -v
```

Expected: all tests pass.

---

### Step 11.3: 本地启动检查（不连接真实服务）

Run a quick import/smoke test:

```bash
python -c "import web.app, telegram_client, config; print('imports ok')"
```

Expected: `imports ok` (assuming env vars are set or use a test `.env`).

---

### Step 11.4: 提交

```bash
git add tests/test_helpers.py
git commit -m "test: add helper unit tests and local smoke check"
```

---

## Task 12: 文档同步

**目标：** 更新 `README.md` 和 `AGENTS.md` 以反映新结构、环境变量和部署方式。

**Files:**
- Modify: `README.md`, `AGENTS.md`, `project_log.md`

---

### Step 12.1: 重写 `README.md` 关键章节

- 主程序改为 `main.py`。
- 列出新增环境变量：`MONGODB_URI`, `DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD`, `DASHBOARD_PORT`。
- 删除 `supervisord.conf` 切换版本的说明。
- 删除 Volume/ `DATA_DIR` 说明，改为 MongoDB addon 说明。
- 增加首次部署后访问 `/login` 完成 Telegram 登录的说明。

---

### Step 12.2: 更新 `AGENTS.md`

- 更新“当前主程序”为 `main.py`。
- 更新技术栈（移除 supervisor，新增 pymongo/MongoDB）。
- 更新项目结构。
- 更新部署说明（MongoDB addon、环境变量、`/health`）。

---

### Step 12.3: 更新 `project_log.md`

- 记录本次重构决策：模块化、MongoDB 持久化、StringSession、Dashboard。

---

### Step 12.4: 提交

```bash
git add README.md AGENTS.md project_log.md
git commit -m "docs: update README, AGENTS and project log for tgBot Lite"
```

---

## Task 13: 最终验证与交付

**目标：** 做一次完整的本地启动尝试（可选 Docker 构建），确认 `/health` 可访问。

---

### Step 13.1: 构建 Docker 镜像

```bash
cd /Users/will/Cursor\ Project/NFtgBotV2
docker build -t tgbot-lite:latest .
```

Expected: image builds successfully.

---

### Step 13.2: 本地容器启动（需要 env 文件）

```bash
docker run -d --name tgbot-lite-test \
  -p 8000:8000 \
  --env-file .env \
  tgbot-lite:latest
```

---

### Step 13.3: 验证 `/health`

```bash
sleep 5
curl -s http://localhost:8000/health | python3 -m json.tool
```

Expected JSON:

```json
{
    "status": "ok",
    "telegram_connected": false,
    "startup_time": "..."
}
```

`telegram_connected` may be `false` until login is completed.

---

### Step 13.4: 停止并删除测试容器

```bash
docker stop tgbot-lite-test && docker rm tgbot-lite-test
```

---

## Self-Review Checklist

1. **Spec coverage:**
   - 模块化 ✅ Task 5-9
   - MongoDB 持久化 ✅ Task 3
   - StringSession ✅ Task 8
   - Dashboard ✅ Task 9
   - 删除旧文件/依赖 ✅ Task 1
   - `/health` 探针 ✅ Task 9
   - 日志缓冲/减少噪音 ✅ Task 7
   - 文档同步 ✅ Task 12
2. **Placeholder scan:** 无 TBD/TODO。
3. **Type consistency:**
   - `OKXAccount` 方法名在 Task 5 与 Task 9 `get_orders` 一致。
   - `processor.log_buffer` 为 `deque`，Task 7 与 Task 9 一致。
   - `telegram_client.client` 类型一致。
4. **Northflank 适配：** Dockerfile 直接启动，`EXPOSE 8000`，`/health` 无需认证。
