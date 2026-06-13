import logging
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


