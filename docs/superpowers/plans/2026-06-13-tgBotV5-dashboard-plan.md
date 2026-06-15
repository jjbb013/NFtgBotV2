# tgBotV5 Web Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-_SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `tgBotV5.py` that merges the existing Telegram signal trading bot with a FastAPI web dashboard, allowing users to check Telegram/OKX status, view logs, and re-login to Telegram from a browser.

**Architecture:** A single Python process runs both the Telethon listener and FastAPI. They share the same asyncio event loop. The dashboard uses HTTP Basic Auth, Jinja2 templates, and a small amount of inline JavaScript. OKX SDK calls run in a thread pool to avoid blocking the event loop. Logs are captured into a memory buffer for web display with sensitive data filtered out.

**Tech Stack:** Python 3.11, Telethon, FastAPI, Uvicorn, Jinja2, python-okx, existing `utils.py`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `tgBotV5.py` | Main entry point. Contains config, Telegram client management, signal handling (mirrored from `tgBotV4.py`), OKX queries, log buffer, FastAPI routes, and the combined startup logic. |
| `templates/dashboard.html` | Single-page Jinja2 dashboard template. |
| `static/dashboard.css` | Dashboard styles. |
| `static/dashboard.js` | Frontend interactions: refresh buttons, Telegram login wizard. |
| `supervisord.conf` | Update to run `tgBotV5.py`. |
| `README.md` / `AGENTS.md` / `project_log.md` | Document V5, new env vars, deployment steps. |

---

## Task 1: Create Feature Branch

**Files:**
- Modify: `.git/HEAD` (via git command)

- [ ] **Step 1: Create and switch to feature branch**

Run:
```bash
git checkout -b feat/tgBotV5-dashboard
```

- [ ] **Step 2: Verify branch**

Run:
```bash
git branch --show-current
```
Expected output: `feat/tgBotV5-dashboard`

- [ ] **Step 3: Commit initial plan/doc update**

Run:
```bash
git add docs/superpowers/specs/2026-06-13-tgBotV5-web-dashboard-design.md
git commit -m "docs: add tgBotV5 web dashboard design spec"
```

---

## Task 2: Create Directory Structure and Empty Files

**Files:**
- Create: `tgBotV5.py`
- Create: `templates/dashboard.html`
- Create: `static/dashboard.css`
- Create: `static/dashboard.js`

- [ ] **Step 1: Create directories and empty files**

Run:
```bash
mkdir -p templates static
touch tgBotV5.py templates/dashboard.html static/dashboard.css static/dashboard.js
```

- [ ] **Step 2: Commit**

Run:
```bash
git add tgBotV5.py templates/dashboard.html static/dashboard.css static/dashboard.js
git commit -m "chore: scaffold tgBotV5 files"
```

---

## Task 3: Implement Log Buffer Handler

**Files:**
- Modify: `tgBotV5.py` (top section)

This handler captures log records into a thread-safe in-memory deque so the dashboard can display recent logs without reading files.

- [ ] **Step 1: Add imports and LogBufferHandler class**

Insert at the top of `tgBotV5.py` after the existing import block that will be added later:

```python
from collections import deque
import threading

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
```

- [ ] **Step 2: Configure logging to use the buffer**

Add immediately after the class definition:

```python
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
```

- [ ] **Step 3: Test the handler**

Append a temporary test block at the bottom of `tgBotV5.py`:

```python
if __name__ == '__main__':
    logger.info('test info message')
    logger.error('test error message')
    assert len(log_buffer.get_lines(10)) == 2
    print('log buffer test passed')
```

Run:
```bash
python tgBotV5.py
```
Expected output includes `log buffer test passed` and two log lines.

- [ ] **Step 4: Remove temporary test block and commit**

Remove the temporary `if __name__ == '__main__':` block.

Run:
```bash
git add tgBotV5.py
git commit -m "feat: add in-memory log buffer handler"
```

---

## Task 4: Implement Sensitive Data Filtering

**Files:**
- Modify: `tgBotV5.py`

This function masks phone numbers, API keys, passwords, passphrases, and verification codes in log lines shown on the web.

- [ ] **Step 1: Add sanitize_log function**

Insert into `tgBotV5.py`:

```python
import re

SENSITIVE_PATTERNS = [
    (re.compile(r'\+?1?\d{9,15}'), '***PHONE***'),
    (re.compile(r'api[_-]?key\s*[:=]\s*["\']?[a-zA-Z0-9_-]+["\']?'), 'api_key=***'),
    (re.compile(r'secret[_-]?key\s*[:=]\s*["\']?[a-zA-Z0-9_-]+["\']?'), 'secret_key=***'),
    (re.compile(r'passphrase\s*[:=]\s*["\']?[^"\'\s]+["\']?'), 'passphrase=***'),
    (re.compile(r'password\s*[:=]\s*["\']?[^"\'\s]+["\']?'), 'password=***'),
    (re.compile(r'code\s*[:=]\s*["\']?\d{5,6}["\']?'), 'code=***'),
    (re.compile(r'bark[_-]?key\s*[:=]\s*["\']?[a-zA-Z0-9_-]+["\']?'), 'bark_key=***'),
]

def sanitize_log(line: str) -> str:
    for pattern, replacement in SENSITIVE_PATTERNS:
        line = pattern.sub(replacement, line, flags=re.IGNORECASE)
    return line
```

- [ ] **Step 2: Add unit test in tgBotV5.py**

Append a temporary test block:

```python
if __name__ == '__main__':
    sample = 'api_key=abc123 secret_key=xyz passphrase=mysecret code=123456 +8619334015105'
    masked = sanitize_log(sample)
    assert '***' in masked
    assert 'abc123' not in masked
    assert 'mysecret' not in masked
    assert '123456' not in masked
    assert '+8619334015105' not in masked
    print('sanitize test passed')
```

Run:
```bash
python tgBotV5.py
```
Expected output: `sanitize test passed`

- [ ] **Step 3: Remove test block and commit**

Run:
```bash
git add tgBotV5.py
git commit -m "feat: add log sanitization for sensitive data"
```

---

## Task 5: Implement Config Loading

**Files:**
- Modify: `tgBotV5.py`

Load environment variables and validate required ones. Fail fast if critical config is missing.

- [ ] **Step 1: Add config section**

Insert into `tgBotV5.py`:

```python
from dotenv import load_dotenv

load_dotenv('.env')

TG_API_ID = os.getenv('TG_API_ID')
TG_API_HASH = os.getenv('TG_API_HASH')
TG_LOG_GROUP_ID = os.getenv('TG_LOG_GROUP_ID')
TG_CHANNEL_IDS = os.getenv('TG_CHANNEL_IDS', '')
PATCH_MISSING_SIGNALS_INTERVAL = int(os.getenv('PATCH_MISSING_SIGNALS_INTERVAL', 30))
HEALTH_CHECK_INTERVAL = int(os.getenv('HEALTH_CHECK_INTERVAL', 300))

DASHBOARD_USERNAME = os.getenv('DASHBOARD_USERNAME')
DASHBOARD_PASSWORD = os.getenv('DASHBOARD_PASSWORD')
DASHBOARD_PORT = int(os.getenv('DASHBOARD_PORT', '8000'))

if not all([TG_API_ID, TG_API_HASH, TG_CHANNEL_IDS]):
    logger.error('关键环境变量 TG_API_ID, TG_API_HASH, TG_CHANNEL_IDS 未配置')
    sys.exit(1)

if not all([DASHBOARD_USERNAME, DASHBOARD_PASSWORD]):
    logger.error('Web Dashboard 环境变量 DASHBOARD_USERNAME, DASHBOARD_PASSWORD 未配置')
    sys.exit(1)

TG_API_ID = int(TG_API_ID)
TG_LOG_GROUP_ID = int(TG_LOG_GROUP_ID) if TG_LOG_GROUP_ID else None
CHANNEL_IDS = [int(cid.strip()) for cid in TG_CHANNEL_IDS.split(',') if cid.strip()]

DATA_DIR = os.getenv('DATA_DIR', './data')
SESSION_DIR = os.getenv('SESSION_DIR', './data/sessions')
os.makedirs(SESSION_DIR, exist_ok=True)
LAST_SESSION_PATH_FILE = os.path.join(SESSION_DIR, '../last_session_path.txt')
```

- [ ] **Step 2: Commit**

Run:
```bash
git add tgBotV5.py
git commit -m "feat: add environment configuration loading"
```

---

## Task 6: Port Session Management and Account Loading from tgBotV4

**Files:**
- Modify: `tgBotV5.py`

Copy `get_session_file()` and `get_test_accounts()` from `tgBotV4.py` with minor adjustments (logger name).

- [ ] **Step 1: Add session management functions**

Insert into `tgBotV5.py`:

```python
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


def get_test_accounts():
    accounts = []
    for i in range(1, 6):
        prefix = f'OKX{i}_'
        if all(os.getenv(prefix + k) for k in ['API_KEY', 'SECRET_KEY', 'PASSPHRASE']):
            account_name = os.getenv(f'OKX{i}_ACCOUNT_NAME', f'OKX{i}')
            accounts.append({
                'account_idx': i, 'account_name': account_name,
                'API_KEY': os.getenv(prefix + 'API_KEY'),
                'SECRET_KEY': os.getenv(prefix + 'SECRET_KEY'),
                'PASSPHRASE': os.getenv(prefix + 'PASSPHRASE'),
                'FLAG': os.getenv(prefix + 'FLAG', '0')
            })
    logger.info(f"共加载 {len(accounts)} 个有效OKX账户")
    return accounts
```

- [ ] **Step 2: Commit**

Run:
```bash
git add tgBotV5.py
git commit -m "feat: port session management and OKX account loading"
```

---

## Task 7: Implement OKX Data Query Module

**Files:**
- Modify: `tgBotV5.py`

Add async wrappers around OKX SDK calls. All SDK calls run in `asyncio.to_thread`.

- [ ] **Step 1: Add imports and OKX query functions**

Insert into `tgBotV5.py`:

```python
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
        if resp.get('code') == '0':
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
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        resp = await asyncio.to_thread(
            acc_api.get_account_bills,
            instType='SWAP',
            mgnMode='cross',
            begin=start.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
            end=end.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
            limit='100'
        )
        if resp.get('code') == '0':
            total = 0.0
            for item in resp.get('data', []):
                pnl = item.get('pnl')
                if pnl is not None:
                    try:
                        total += float(pnl)
                    except (ValueError, TypeError):
                        continue
            return round(total, 4)
        logger.error(f"[{account['account_name']}] 获取账单失败: {resp.get('msg')}")
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
```

- [ ] **Step 2: Commit**

Run:
```bash
git add tgBotV5.py
git commit -m "feat: add async OKX status query module"
```

---

## Task 8: Implement Git and Version Info Helpers

**Files:**
- Modify: `tgBotV5.py`

Read current git commit and determine which bot version supervisord is configured to run.

- [ ] **Step 1: Add helper functions**

Insert into `tgBotV5.py`:

```python
def get_git_info():
    for cwd in ['/app', '.']:
        try:
            commit_hash = subprocess.check_output(
                ['git', 'rev-parse', '--short', 'HEAD'], cwd=cwd, text=True
            ).strip()
            commit_msg = subprocess.check_output(
                ['git', 'log', '-1', '--pretty=%s'], cwd=cwd, text=True
            ).strip()
            commit_time = subprocess.check_output(
                ['git', 'log', '-1', '--pretty=%ci'], cwd=cwd, text=True
            ).strip()
            return {
                'hash': commit_hash,
                'message': commit_msg,
                'time': commit_time,
            }
        except Exception:
            continue
    logger.warning('获取 git 信息失败')
    return {'hash': 'unknown', 'message': 'unknown', 'time': 'unknown'}


def get_active_version():
    for path in ['/app/supervisord.conf', './supervisord.conf']:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            match = re.search(r'command=python\s+\./(tgBotV\d+\.py)', content)
            if match:
                return match.group(1)
        except Exception:
            continue
    logger.warning('读取 supervisord.conf 失败')
    return 'unknown'
```

- [ ] **Step 2: Commit**

Run:
```bash
git add tgBotV5.py
git commit -m "feat: add git and active version helpers"
```

---

## Task 9: Implement FastAPI App, Auth, and Dashboard Route

**Files:**
- Modify: `tgBotV5.py`
- Modify: `templates/dashboard.html`
- Modify: `static/dashboard.css`
- Modify: `static/dashboard.js`

Set up FastAPI with static files, templates, HTTP Basic Auth, and the main dashboard page.

- [ ] **Step 1: Add FastAPI imports and auth setup**

Insert into `tgBotV5.py`:

```python
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
import secrets

app = FastAPI()
security = HTTPBasic()

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
```

- [ ] **Step 2: Add dashboard route**

Insert into `tgBotV5.py`:

```python
@app.get('/', response_class=HTMLResponse)
async def dashboard(request: Request, username: str = Depends(verify_credentials)):
    return templates.TemplateResponse('dashboard.html', {
        'request': request,
        'username': username,
        'channel_ids': CHANNEL_IDS,
    })
```

- [ ] **Step 3: Create minimal dashboard.html**

Write to `templates/dashboard.html`:

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TgBotV5 Dashboard</title>
    <link rel="stylesheet" href="/static/dashboard.css">
</head>
<body>
    <header>
        <h1>Telegram 信号交易机器人 V5</h1>
        <span id="current-time">--</span>
        <button onclick="refreshAll()">刷新全部</button>
    </header>

    <main>
        <section id="system-status">
            <h2>系统状态</h2>
            <div id="system-status-content">加载中...</div>
        </section>

        <section id="telegram-status">
            <h2>Telegram 状态</h2>
            <div id="telegram-status-content">加载中...</div>
            <button id="relogin-btn" style="display:none;" onclick="showLoginWizard()">重新登录</button>
        </section>

        <section id="login-wizard" style="display:none;">
            <h3>Telegram 重新登录</h3>
            <div id="login-step-1">
                <input type="text" id="phone" placeholder="手机号，如 +8612345678901">
                <button onclick="startLogin()">获取验证码</button>
            </div>
            <div id="login-step-2" style="display:none;">
                <input type="text" id="code" placeholder="验证码">
                <button onclick="verifyCode()">验证</button>
            </div>
            <div id="login-step-3" style="display:none;">
                <input type="password" id="password" placeholder="二步验证密码">
                <button onclick="verifyPassword()">完成登录</button>
            </div>
            <div id="login-result"></div>
        </section>

        <section id="okx-status">
            <h2>OKX 账户</h2>
            <div id="okx-status-content">加载中...</div>
        </section>

        <section id="logs">
            <h2>运行日志 <button onclick="refreshLogs()">刷新日志</button></h2>
            <pre id="logs-content">加载中...</pre>
        </section>
    </main>

    <script src="/static/dashboard.js"></script>
</body>
</html>
```

- [ ] **Step 4: Create minimal dashboard.css**

Write to `static/dashboard.css`:

```css
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    margin: 0;
    padding: 1rem;
    background: #f5f5f5;
    color: #333;
}
header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    margin-bottom: 1rem;
}
header h1 {
    margin: 0;
    font-size: 1.25rem;
}
section {
    background: #fff;
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
h2 {
    margin-top: 0;
    font-size: 1.1rem;
}
button {
    padding: 0.4rem 0.8rem;
    margin: 0.2rem;
    cursor: pointer;
}
pre {
    background: #1e1e1e;
    color: #d4d4d4;
    padding: 1rem;
    border-radius: 4px;
    overflow-x: auto;
    max-height: 400px;
    overflow-y: auto;
}
input {
    padding: 0.4rem;
    margin: 0.2rem;
}
```

- [ ] **Step 5: Create minimal dashboard.js**

Write to `static/dashboard.js`:

```javascript
function updateTime() {
    document.getElementById('current-time').textContent = new Date().toLocaleString('zh-CN');
}
setInterval(updateTime, 1000);
updateTime();

async function refreshAll() {
    await Promise.all([
        refreshSystemStatus(),
        refreshTelegramStatus(),
        refreshOKXStatus(),
        refreshLogs(),
    ]);
}

async function apiGet(path) {
    const resp = await fetch(path);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}

async function apiPost(path, body) {
    const resp = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    return resp.json();
}

async function refreshSystemStatus() {
    const data = await apiGet('/api/system/status');
    document.getElementById('system-status-content').innerHTML = `
        <p>运行版本: ${data.active_version}</p>
        <p>Git: ${data.git.hash} - ${data.git.message}</p>
        <p>提交时间: ${data.git.time}</p>
    `;
}

async function refreshTelegramStatus() {
    const data = await apiGet('/api/telegram/status');
    let html = `
        <p>Session 文件: ${data.session_path}</p>
        <p>登录状态: ${data.authorized ? '有效' : '失效'}</p>
        <p>连接状态: ${data.connected ? '在线' : '离线'}</p>
        <p>监听频道: ${data.channel_ids.join(', ')}</p>
    `;
    if (data.me) {
        html += `<p>当前用户: ${data.me.first_name} ${data.me.last_name || ''} (@${data.me.username || ''})</p>`;
    }
    document.getElementById('telegram-status-content').innerHTML = html;
    document.getElementById('relogin-btn').style.display = data.authorized ? 'none' : 'inline-block';
}

async function refreshOKXStatus() {
    const data = await apiGet('/api/okx/status');
    let html = '';
    for (const acc of data.accounts) {
        html += `
            <div class="okx-card">
                <h3>${acc.name}</h3>
                <p>连接: ${acc.connected ? '正常' : '异常'}</p>
                <p>USDT 余额: ${acc.balance !== null ? acc.balance : '获取失败'}</p>
                <p>最近 7 天盈亏: ${acc.pnl !== null ? acc.pnl + ' USDT' : '获取失败'}</p>
                <button onclick="loadOrders('${acc.name}')">查看最近 20 条订单</button>
                <div id="orders-${acc.name}"></div>
            </div>
        `;
    }
    document.getElementById('okx-status-content').innerHTML = html || '没有配置 OKX 账户';
}

async function loadOrders(accountName) {
    const data = await apiGet(`/api/okx/orders?account=${encodeURIComponent(accountName)}`);
    let html = '<table border="1" cellpadding="5"><tr><th>标的</th><th>方向</th><th>持仓方向</th><th>数量</th><th>均价</th><th>状态</th><th>时间</th></tr>';
    for (const o of data.orders) {
        html += `<tr><td>${o.instId}</td><td>${o.side}</td><td>${o.posSide}</td><td>${o.sz}</td><td>${o.avgPx}</td><td>${o.state}</td><td>${new Date(parseInt(o.cTime)).toLocaleString('zh-CN')}</td></tr>`;
    }
    html += '</table>';
    document.getElementById(`orders-${accountName}`).innerHTML = html;
}

async function refreshLogs() {
    const data = await apiGet('/api/logs');
    document.getElementById('logs-content').textContent = data.lines.join('\n');
}

let loginState = {};

function showLoginWizard() {
    document.getElementById('login-wizard').style.display = 'block';
}

async function startLogin() {
    const phone = document.getElementById('phone').value;
    const result = await apiPost('/api/telegram/login/start', { phone });
    loginState = { phone, phone_code_hash: result.phone_code_hash };
    document.getElementById('login-step-1').style.display = 'none';
    document.getElementById('login-step-2').style.display = 'block';
    document.getElementById('login-result').textContent = result.message || '';
}

async function verifyCode() {
    const code = document.getElementById('code').value;
    const result = await apiPost('/api/telegram/login/verify', {
        phone: loginState.phone,
        code,
        phone_code_hash: loginState.phone_code_hash,
    });
    if (result.need_password) {
        document.getElementById('login-step-2').style.display = 'none';
        document.getElementById('login-step-3').style.display = 'block';
    } else {
        finishLogin(result);
    }
}

async function verifyPassword() {
    const password = document.getElementById('password').value;
    const result = await apiPost('/api/telegram/login/password', { password });
    finishLogin(result);
}

function finishLogin(result) {
    document.getElementById('login-result').textContent = result.success ? '登录成功' : `登录失败: ${result.error}`;
    if (result.success) {
        setTimeout(() => location.reload(), 2000);
    }
}

refreshAll();
```

- [ ] **Step 6: Commit**

Run:
```bash
git add tgBotV5.py templates/dashboard.html static/dashboard.css static/dashboard.js
git commit -m "feat: add FastAPI skeleton, auth, and dashboard UI"
```

---

## Task 10: Implement Dashboard API Endpoints

**Files:**
- Modify: `tgBotV5.py`

Add the backend API endpoints consumed by `dashboard.js`.

- [ ] **Step 1: Add system status endpoint**

Insert into `tgBotV5.py`:

```python
@app.get('/api/system/status')
async def system_status(username: str = Depends(verify_credentials)):
    return {
        'active_version': get_active_version(),
        'git': get_git_info(),
    }
```

- [ ] **Step 2: Add Telegram status endpoint**

Insert into `tgBotV5.py`:

```python
@app.get('/api/telegram/status')
async def telegram_status(username: str = Depends(verify_credentials)):
    session_path = get_session_file()
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
```

- [ ] **Step 3: Add OKX status endpoint**

Insert into `tgBotV5.py`:

```python
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
```

- [ ] **Step 4: Add OKX orders endpoint**

Insert into `tgBotV5.py`:

```python
from fastapi import Query

@app.get('/api/okx/orders')
async def okx_orders(
    account: str = Query(...),
    username: str = Depends(verify_credentials)
):
    target = next((a for a in TEST_ACCOUNTS if a['account_name'] == account), None)
    if not target:
        raise HTTPException(status_code=404, detail='Account not found')
    orders = await get_recent_orders(target, limit=20)
    return {'orders': orders}
```

- [ ] **Step 5: Add logs endpoint**

Insert into `tgBotV5.py`:

```python
@app.get('/api/logs')
async def logs(username: str = Depends(verify_credentials)):
    raw_lines = log_buffer.get_lines(100)
    sanitized = [sanitize_log(line) for line in raw_lines]
    return {'lines': sanitized}
```

- [ ] **Step 6: Commit**

Run:
```bash
git add tgBotV5.py
git commit -m "feat: add dashboard API endpoints"
```

---

## Task 11: Port Signal Processing Logic from tgBotV4

**Files:**
- Modify: `tgBotV5.py`

Copy signal extraction, order placement, close position, and message handler from `tgBotV4.py`.

- [ ] **Step 1: Copy signal extraction functions**

Ensure the file has this import at the top (add if missing):

```python
from telethon import events
```

Insert into `tgBotV5.py`:

```python
def extract_trade_info(message):
    logger.debug(f"正在从消息中提取交易信息: {message[:100]}...")
    close_keywords = ['空止盈', '空止损', '多止盈', '多止损', '平多', '平空', 'MA止损','MA 止损']
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
    if any(kw in message for kw in ['执行交易:MA止损', 'MA止损','MA 止损']):
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
        symbol = symbol_match.group(1).upper().replace('USDT.P', '').replace('USDT','')
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
```

- [ ] **Step 2: Copy processed IDs helpers**

Insert into `tgBotV5.py`:

```python
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
```

- [ ] **Step 3: Copy OKX trading functions from tgBotV4**

Insert into `tgBotV5.py`:

```python
from utils import get_shanghai_time, send_bark_notification, build_order_params, set_account_leverage
import okx.PublicData as PublicData

async def get_latest_market_price(symbol):
    try:
        api = MarketData.MarketAPI(flag='0', debug=False)
        response = await asyncio.to_thread(api.get_ticker, instId=f"{symbol.upper()}-USDT-SWAP")
        if response['code'] == '0':
            return float(response['data'][0]['last'])
        logger.error(f"获取 {symbol} 价格失败: {response['msg']}")
    except Exception as e:
        logger.error(f"获取 {symbol} 价格异常: {e}")
    return None


async def convert_coin_to_contract_size(inst_id, px, sz, flag):
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
        if result['code'] == '0' and result['data']:
            converted_sz = float(result['data'][0]['sz'])
            logger.info(f"币张转换成功: {sz} USDT 价值 转换为 {converted_sz} 张合约 ({inst_id})")
            return converted_sz
        else:
            logger.error(f"币张转换失败: {result.get('msg', '未知错误')}")
    except Exception as e:
        logger.error(f"币张转换异常: {e}")
    return None


async def place_okx_order(account, action, symbol, size):
    try:
        api = Trade.TradeAPI(account['API_KEY'], account['SECRET_KEY'], account['PASSPHRASE'], False, account['FLAG'])
        price = await get_latest_market_price(symbol)
        if not price:
            return {"success": False, "error_msg": "无法获取市场价格"}

        tp_ratio = float(os.getenv(f"OKX{account['account_idx']}_TP_RATIO", '0.01'))
        sl_ratio = float(os.getenv(f"OKX{account['account_idx']}_SL_RATIO", '0.027'))

        side, pos_side = ('buy', 'long') if action == '做多' else ('sell', 'short')
        tp_price = price * (1 + (tp_ratio if side == 'buy' else -tp_ratio))
        sl_price = price * (1 - (sl_ratio if side == 'buy' else -sl_ratio))

        params = build_order_params(f"{symbol}-USDT-SWAP", side, price, size, pos_side, round(tp_price, 4), round(sl_price, 4))
        logger.info(f"下单参数: {json.dumps(params, indent=2)}")
        resp = await asyncio.to_thread(api.place_order, **params)
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

        resp = await asyncio.to_thread(acc_api.get_positions, instId=inst_id)
        if resp['code'] != '0':
            return {"success": False, "error_msg": "获取持仓失败"}

        results = []
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
            if close_resp['code'] == '0' and close_resp['data'][0]['sCode'] == '0':
                results.append({'pos_side': pos_side_to_close, 'size': pos['pos'], 'order_id': close_resp['data'][0]['ordId']})
            else:
                logger.error(f"[{account['account_name']}] 平仓 {pos_side_to_close} {symbol} 失败: {close_resp['data'][0]['sMsg']}")
                results.append({'pos_side': pos_side_to_close, 'size': pos['pos'], 'error_msg': close_resp['data'][0]['sMsg']})
        return {"success": True, "close_results": results, "okx_resp": resp, "total_upl": total_upl, "pnl_pct": pnl_pct}
    except Exception as e:
        logger.error(f"平仓异常: {e}")
        return {"success": False, "error_msg": str(e)}
```

- [ ] **Step 4: Copy signal processors**

Insert into `tgBotV5.py`:

```python
async def process_open_signal(action, symbol, msg_text):
    log_header = f"【补单】\n原始信息: {msg_text}" if "补单" in msg_text else f"【实时信号】\n原始信息: {msg_text}"
    for account in TEST_ACCOUNTS:
        balance = await get_usdt_balance(account)
        if balance is None:
            logger.error(f"无法获取账户 {account['account_name']} 的余额，跳过下单。")
            continue

        position_ratio = float(os.getenv(f"OKX{account['account_idx']}_POSITION_RATIO", "0.25"))
        margin = balance * position_ratio
        leverage = int(os.getenv(f"OKX{account['account_idx']}_LEVERAGE", "10"))
        price = await get_latest_market_price(symbol)
        if not price:
            logger.error(f"无法获取 {symbol} 的市场价格，跳过下单。")
            continue

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

        result = await place_okx_order(account, action, symbol, size)
        conversion_log = f"币张转换成功: {order_value:.4f} USDT 价值 转换为 {size:.4f} 张合约 ({inst_id})"
        full_log = f"{conversion_log}\n{order_details}"

        if TG_LOG_GROUP_ID:
            log_to_send = full_log if len(full_log) <= 4090 else f"{full_log[:4000]}...\n(消息过长，已截断，请查看本地日志)"
            await client.send_message(TG_LOG_GROUP_ID, log_to_send)

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
        send_bark_notification(bark_title, bark_content)

        original_signal_log = f"{log_header}\n信号判断: {action} {symbol} (账户: {account['account_name']})\n操作返回: {json.dumps(result, ensure_ascii=False, indent=2)}"
        logger.info(original_signal_log)
        if TG_LOG_GROUP_ID:
            log_to_send = original_signal_log if len(original_signal_log) <= 4090 else f"{original_signal_log[:4000]}...\n(消息过长，已截断，请查看本地日志)"
            await client.send_message(TG_LOG_GROUP_ID, log_to_send)


async def process_close_signal(close_type, symbol, msg_text):
    log_header = f"【补单】\n原始信息: {msg_text}" if "补单" in msg_text else f"【实时信号】\n原始信息: {msg_text}"
    for account in TEST_ACCOUNTS:
        if symbol is None:
            error_msg = f"[{account['account_name']}] 平仓信号 ({close_type}) 未能提取交易对，跳过平仓。"
            logger.error(error_msg)
            if TG_LOG_GROUP_ID:
                await client.send_message(TG_LOG_GROUP_ID, f"{log_header}\n{error_msg}")
            send_bark_notification(f"⚠️ 平仓失败 ⚠️", error_msg)
            continue

        result = await close_okx_position(account, symbol, close_type)
        bark_title = f"Tg信号策略平仓-{symbol}"
        content = build_close_bark_content(
            close_type, symbol, account['account_name'], result.get('close_results', []),
            result.get('okx_resp'), result.get('error_msg'), result.get('total_upl'), result.get('pnl_pct')
        )
        full_log = f"{log_header}\n信号判断: 平仓 {close_type} {symbol} (账户: {account['account_name']})\n操作返回: {json.dumps(result, ensure_ascii=False, indent=2)}"
        logger.info(full_log)
        if TG_LOG_GROUP_ID:
            log_to_send = full_log if len(full_log) <= 4090 else f"{full_log[:4000]}...\n(消息过长，已截断，请查看本地日志)"
            await client.send_message(TG_LOG_GROUP_ID, log_to_send)
        send_bark_notification(bark_title, content)


def build_close_bark_content(close_type, symbol, account_name, close_results, okx_resp=None, error_msg=None, total_upl=None, pnl_pct=None):
    now = get_shanghai_time()
    lines = [f"账户: {account_name}", f"交易标的: {symbol}", f"信号类型: 平仓{close_type}", f"平仓结果: {len(close_results)} 个持仓", f"时间: {now}"]
    if total_upl is not None:
        pnl_sign = "+" if total_upl >= 0 else ""
        if pnl_pct is not None:
            pct_sign = "+" if pnl_pct >= 0 else ""
            lines.append(f"盈亏: {pnl_sign}{total_upl:.4f} USDT ({pct_sign}{pnl_pct:.2f}%)")
        else:
            lines.append(f"盈亏: {pnl_sign}{total_upl:.4f} USDT")
    if close_results:
        for res in close_results:
            lines.append(f"- {res['pos_side']}: {res['size']} (订单ID: {res['order_id']})")
    if error_msg:
        lines.extend(["⚠️ 平仓失败 ⚠️", f"错误: {error_msg}"])
    if okx_resp:
        lines.extend([f"服务器响应代码: {okx_resp.get('code', '')}", f"服务器响应消息: {okx_resp.get('msg', '')}"])
    return "\n".join(lines)
```

- [ ] **Step 5: Copy message handler and background tasks**

Insert into `tgBotV5.py`:

```python
background_task_refs = []

@client.on(events.NewMessage(chats=CHANNEL_IDS))
async def handler(event):
    msg_text = event.message.text or ''

    if TG_LOG_GROUP_ID:
        forward_msg = f"【消息监听】频道:{event.chat_id}\n时间: {get_shanghai_time()}\n内容: {msg_text}"
        await client.send_message(TG_LOG_GROUP_ID, forward_msg)

    async with signal_lock:
        if event.id in PROCESSED_MESSAGE_IDS.get(event.chat_id, set()):
            return
        PROCESSED_MESSAGE_IDS.setdefault(event.chat_id, set()).add(event.id)
        save_processed_ids(PROCESSED_MESSAGE_IDS)
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
        global PROCESSED_MESSAGE_IDS
        PROCESSED_MESSAGE_IDS = load_processed_ids()
        try:
            for channel_id in CHANNEL_IDS:
                async for msg in client.iter_messages(channel_id, limit=20):
                    if not (msg and msg.text):
                        continue
                    async with signal_lock:
                        if msg.id in PROCESSED_MESSAGE_IDS.get(channel_id, set()):
                            continue
                        PROCESSED_MESSAGE_IDS.setdefault(channel_id, set()).add(msg.id)
                        save_processed_ids(PROCESSED_MESSAGE_IDS)
                        action, symbol = extract_trade_info(msg.text)
                        if action and symbol:
                            await process_open_signal(action, symbol, f"补单: {msg.text}")
                        close_type, close_symbol = extract_close_signal(msg.text)
                        if close_type and close_symbol:
                            await process_close_signal(close_type, close_symbol, f"补单: {msg.text}")
        except Exception as e:
            logger.error(f"历史消息补单检查异常: {e}")


async def set_leverage_for_all_accounts():
    logger.info("正在为所有账户设置杠杆...")
    for account in TEST_ACCOUNTS:
        leverage = os.getenv(f"OKX{account['account_idx']}_LEVERAGE", "10")
        for symbol in ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]:
            try:
                result = set_account_leverage(
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


async def init_processed_ids():
    logger.info("正在初始化消息ID缓存...")
    for channel_id in CHANNEL_IDS:
        PROCESSED_MESSAGE_IDS.setdefault(channel_id, set())
        async for message in client.iter_messages(channel_id, limit=50):
            if message:
                PROCESSED_MESSAGE_IDS[channel_id].add(message.id)
    save_processed_ids(PROCESSED_MESSAGE_IDS)
    logger.info("消息ID缓存初始化完成。")
```

- [ ] **Step 6: Commit**

Run:
```bash
git add tgBotV5.py
git commit -m "feat: port signal processing and trading logic from tgBotV4"
```

---

## Task 12: Implement Telegram Web Re-login Flow

**Files:**
- Modify: `tgBotV5.py`

Handle the multi-step Telegram login in the same asyncio loop.

- [ ] **Step 1: Add global login state and helper**

Insert into `tgBotV5.py`:

```python
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
    background_task_refs = [
        asyncio.create_task(check_and_patch_missing_signals()),
        asyncio.create_task(health_check()),
    ]
    logger.info('后台任务已启动')


async def replace_client(new_client):
    global client
    if client and client.is_connected():
        try:
            await client.disconnect()
        except Exception as e:
            logger.warning(f'断开旧 client 时出错: {e}')
    client = new_client
    # Re-register event handler defined in Task 11
    client.on(events.NewMessage(chats=CHANNEL_IDS))(handler)
```

- [ ] **Step 2: Add login start endpoint**

Insert into `tgBotV5.py`:

```python
from pydantic import BaseModel

class PhoneRequest(BaseModel):
    phone: str

@app.post('/api/telegram/login/start')
async def telegram_login_start(
    req: PhoneRequest,
    username: str = Depends(verify_credentials)
):
    global login_state
    await stop_background_tasks()
    if client and client.is_connected():
        try:
            await client.disconnect()
        except Exception as e:
            logger.warning(f'断开当前 client 时出错: {e}')

    session_path = get_session_file()
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
        await start_background_tasks()
        return {'success': False, 'error': str(e)}
```

- [ ] **Step 3: Add code verification endpoint**

Insert into `tgBotV5.py`:

```python
class CodeRequest(BaseModel):
    phone: str
    code: str
    phone_code_hash: str

@app.post('/api/telegram/login/verify')
async def telegram_login_verify(
    req: CodeRequest,
    username: str = Depends(verify_credentials)
):
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
    except Exception as e:
        err_str = str(e)
        if 'Two-steps verification' in err_str or 'SESSION_PASSWORD_NEEDED' in err_str:
            return {'success': True, 'need_password': True, 'message': '需要二步验证密码'}
        logger.error(f'验证码登录失败: {e}')
        await cleanup_login(temp_client)
        return {'success': False, 'error': err_str}
```

- [ ] **Step 4: Add password endpoint and finalization helpers**

Insert into `tgBotV5.py`:

```python
class PasswordRequest(BaseModel):
    password: str

async def finalize_login(new_client):
    global login_state
    await replace_client(new_client)
    session_path = get_session_file()
    os.chmod(session_path, 0o600)
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
```

- [ ] **Step 5: Commit**

Run:
```bash
git add tgBotV5.py
git commit -m "feat: implement Telegram web re-login flow"
```

---

## Task 13: Wire Up Main Entry Point

**Files:**
- Modify: `tgBotV5.py`

Implement `main()` that starts Telegram client, initializes state, launches background tasks, and starts the uvicorn server in the same event loop.

`stop_background_tasks()` and `start_background_tasks()` were already implemented in Task 12.

- [ ] **Step 1: Implement main function**

Insert at the bottom of `tgBotV5.py`:

```python
async def main():
    global client
    session_file = get_session_file()
    client = TelegramClient(session_file, TG_API_ID, TG_API_HASH)

    await client.start()
    logger.info(f'已登录 Telegram，监听频道: {CHANNEL_IDS}')

    # Register Telegram message handler
    client.on(events.NewMessage(chats=CHANNEL_IDS))(handler)

    await init_processed_ids()
    await set_leverage_for_all_accounts()
    await send_startup_symbol_prices()
    await start_background_tasks()

    logger.info('机器人启动完成，Web Dashboard 将在 %s 端口启动', DASHBOARD_PORT)
    config = uvicorn.Config(
        app,
        host='0.0.0.0',
        port=DASHBOARD_PORT,
        workers=1,
        loop='asyncio',
        log_config=None,
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info('程序退出。')
```

- [ ] **Step 2: Commit**

Run:
```bash
git add tgBotV5.py
git commit -m "feat: wire up main entry point with Telegram and FastAPI"
```

---

## Task 14: Update Supervisor Configuration

**Files:**
- Modify: `supervisord.conf`

- [ ] **Step 1: Replace tgBotV4 with tgBotV5 in supervisord.conf**

Edit `supervisord.conf` to:

```ini
[supervisord]
nodaemon=true

[program:tgBotV5]
command=python ./tgBotV5.py
directory=/app
autostart=true
autorestart=true
stdout_logfile=/app/logs/tgBotV5.out.log
stderr_logfile=/app/logs/tgBotV5.err.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
stderr_logfile_maxbytes=50MB
stderr_logfile_backups=10
```

- [ ] **Step 2: Commit**

Run:
```bash
git add supervisord.conf
git commit -m "chore: update supervisord to run tgBotV5"
```

---

## Task 15: Update Documentation

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `project_log.md`

- [ ] **Step 1: Update README.md**

Add a new section at the top of the version history:

```markdown
### v5 版本 (当前)

- **主程序**: `tgBotV5.py`
- **核心改进**:
    - 新增 Web Dashboard，可通过 Northflank 公开端口查看运行状态。
    - 支持在网页上查看 Telegram 登录/监听状态、OKX 账户状态、历史盈亏、历史订单。
    - 支持在网页上直接重新登录 Telegram。
    - 支持在网页上查看最近 100 条运行日志。

#### v5 新增环境变量

- `DASHBOARD_USERNAME`: Web Dashboard 登录用户名（必填）。
- `DASHBOARD_PASSWORD`: Web Dashboard 登录密码（必填）。
- `DASHBOARD_PORT`: Web Dashboard 端口，默认 `8000`。
```

- [ ] **Step 2: Update AGENTS.md**

Add a row to the version comparison table:

```markdown
| 特性 | tgBotV2 | tgBotV3 | tgBotV4 | tgBotV5 |
|------|---------|---------|---------|---------|
| Web Dashboard | 不支持 | 不支持 | 不支持 | 支持 |
| 网页查看日志 | 不支持 | 不支持 | 不支持 | 支持 |
| 网页 Telegram 重新登录 | 不支持 | 不支持 | 不支持 | 支持 |
```

Update the "当前主程序" line to mention `tgBotV5.py` and add a note that `tgBotV4.py` remains as fallback.

- [ ] **Step 3: Update project_log.md**

Add a changelog entry:

```markdown
## v5 更新

1. **新增 Web Dashboard**：
   - 通过 FastAPI 提供 `/` 页面，使用 HTTP Basic Auth 保护。
   - 展示 Telegram 登录状态、监听频道、OKX 账户余额/盈亏/历史订单。
   - 展示最近 100 条运行日志，自动隐藏敏感信息。
   - 支持网页端 Telegram 重新登录。
2. **架构调整**：
   - `tgBotV5.py` 单进程同时运行 Telegram 监听和 Web 服务，共享 asyncio 事件循环。
   - OKX SDK 调用放入线程池，避免阻塞事件循环。
   - `tgBotV4.py` 保留作为 fallback。
```

- [ ] **Step 4: Commit**

Run:
```bash
git add README.md AGENTS.md project_log.md
git commit -m "docs: update README, AGENTS, and project log for tgBotV5"
```

---

## Task 16: Local Verification

**Files:**
- Modify: `.env` (local test only, do not commit)

- [ ] **Step 1: Create local .env for testing**

Ensure `.env` exists with at least:

```env
TG_API_ID=your_api_id
TG_API_HASH=your_api_hash
TG_CHANNEL_IDS=your_channel_id
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=admin123
```

- [ ] **Step 2: Run syntax check**

Run:
```bash
python -m py_compile tgBotV5.py
```
Expected: no output and exit code 0.

- [ ] **Step 3: Start the server locally**

Run:
```bash
python tgBotV5.py
```

Expected log output includes:
- `已登录 Telegram，监听频道: [...]`
- `机器人启动完成，Web Dashboard 将在 8000 端口启动`

- [ ] **Step 4: Open dashboard in browser**

Visit `http://localhost:8000/`.

Expected:
- Browser prompts for username/password.
- After login, the dashboard loads and shows system status.
- Clicking "刷新全部" populates Telegram status, OKX status, and logs.

- [ ] **Step 5: Verify logs are sanitized**

Check the `/api/logs` endpoint or the logs panel on the page.

Expected: no phone numbers, API keys, passwords, or passphrases are visible.

- [ ] **Step 6: Commit verification notes**

Run:
```bash
git add tgBotV5.py templates/dashboard.html static/dashboard.css static/dashboard.js supervisord.conf README.md AGENTS.md project_log.md
git commit -m "feat: tgBotV5 dashboard ready for testing"
```

---

## Task 17: Build Docker Image and Test

**Files:**
- None (uses existing Dockerfile)

- [ ] **Step 1: Build image**

Run:
```bash
docker build -t tg-signal-bot:v5 .
```

Expected: image builds successfully.

- [ ] **Step 2: Run container locally**

Run:
```bash
docker run -d --name tg-signal-bot-v5 \
  -v $PWD/data:/app/data \
  -v $PWD/logs:/app/logs \
  --env-file $PWD/.env \
  -p 8000:8000 \
  tg-signal-bot:v5
```

- [ ] **Step 3: Check logs**

Run:
```bash
docker logs -f tg-signal-bot-v5
```

Expected: supervisord starts `tgBotV5`, Telegram logs in, and FastAPI starts.

- [ ] **Step 4: Clean up test container**

Run:
```bash
docker stop tg-signal-bot-v5
docker rm tg-signal-bot-v5
```

- [ ] **Step 5: Commit any fixes**

If any Docker-related fixes were needed, commit them.

---

## Task 18: Push Branch and Create Pull Request

**Files:**
- None

- [ ] **Step 1: Push branch**

Run:
```bash
git push -u origin feat/tgBotV5-dashboard
```

- [ ] **Step 2: Create pull request**

Use GitHub web UI or CLI:

```bash
gh pr create --title "feat: add tgBotV5 web dashboard" --body "See docs/superpowers/specs/2026-06-13-tgBotV5-web-dashboard-design.md"
```

- [ ] **Step 3: Notify user**

Tell the user the branch is ready for review and Northflank deployment.
