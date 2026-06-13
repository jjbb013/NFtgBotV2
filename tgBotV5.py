import logging
import os
import re
import sys
import threading
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
PATCH_MISSING_SIGNALS_INTERVAL = int(os.getenv('PATCH_MISSING_SIGNALS_INTERVAL', '30'))
HEALTH_CHECK_INTERVAL = int(os.getenv('HEALTH_CHECK_INTERVAL', '300'))

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

