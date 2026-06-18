import sys
from urllib.parse import urlparse
from pymongo import MongoClient
from config import MONGODB_URI

_STATE_ID = 'singleton'
_MAX_IDS_PER_CHANNEL = 1000

# 优先使用 URI 中指定的数据库；若未指定则使用 tgbot_lite
_parsed = urlparse(MONGODB_URI)
_DB_NAME = _parsed.path.lstrip('/') or 'tgbot_lite'

try:
    _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    _client.admin.command('ping')
    _db = _client[_DB_NAME]
    _state = _db['state']
    # 触发一次实际读写权限校验
    _state.find_one({'_id': _STATE_ID})
except Exception as e:
    print(f"[FATAL] 无法连接或认证 MongoDB: {e}", file=sys.stderr)
    print(f"[FATAL] 请确认 MONGODB_URI 正确，且用户对数据库 '{_DB_NAME}' 有读写权限。", file=sys.stderr)
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
