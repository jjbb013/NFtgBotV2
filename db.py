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
