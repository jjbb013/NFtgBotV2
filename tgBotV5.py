import logging
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
    (re.compile(r'(?<![a-zA-Z])api[_-]?key\s*[:=]\s*["\']?[a-zA-Z0-9_-]+["\']?', re.IGNORECASE), 'api_key=***'),
    (re.compile(r'(?<![a-zA-Z])secret[_-]?key\s*[:=]\s*["\']?[a-zA-Z0-9_-]+["\']?', re.IGNORECASE), 'secret_key=***'),
    (re.compile(r'(?<![a-zA-Z])passphrase\s*[:=]\s*["\']?[^"\'\s]+["\']?', re.IGNORECASE), 'passphrase=***'),
    (re.compile(r'(?<![a-zA-Z])password\s*[:=]\s*["\']?[^"\'\s]+["\']?', re.IGNORECASE), 'password=***'),
    (re.compile(r'(?<![a-zA-Z])api[_-]?hash\s*[:=]\s*["\']?[a-zA-Z0-9]+["\']?', re.IGNORECASE), 'api_hash=***'),
    (re.compile(r'(?<![a-zA-Z])bark[_-]?key\s*[:=]\s*["\']?[a-zA-Z0-9_-]+["\']?', re.IGNORECASE), 'bark_key=***'),
    (re.compile(r'(?:verification|verify|auth|otp|telegram|login)\s+code\s*[:=]\s*["\']?\d{5,6}["\']?', re.IGNORECASE), 'code=***'),
]


def sanitize_log(line: str) -> str:
    for pattern, replacement in SENSITIVE_PATTERNS:
        line = pattern.sub(replacement, line)
    return line


