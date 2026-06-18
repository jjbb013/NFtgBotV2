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
