import os
import json
import random
import string
import time
from datetime import datetime, timezone, timedelta
import requests
import okx.Account as Account

def get_shanghai_time(fmt="%Y-%m-%d %H:%M:%S"):
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime(fmt)

def get_env_var(var_name, suffix="", default=None):
    val = os.environ.get(f"{var_name}{suffix}")
    if val is not None:
        return val
    return default

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
        "slTriggerPxType": "last"
    }
    return {
        "instId": inst_id,
        "tdMode": "cross",
        "side": side,
        "ordType": "market",
        "sz": str(size),
        "clOrdId": cl_ord_id,
        "posSide": pos_side,
        "attachAlgoOrds": [attach_algo_ord]
    }

def send_bark_notification(title, content, group=None):
    bark_key = os.getenv("BARK_KEY")
    bark_group = group or os.getenv("BARK_GROUP", "未配置的GROUP")
    if not bark_key:
        print("[WARN] 未配置BARK_KEY，无法发送Bark通知")
        return
    if bark_key.startswith("http"):
        url = bark_key
    else:
        url = f"https://api.day.app/{bark_key}"
    try:
        resp = requests.post(url, json={"title": title, "body": content, "group": bark_group}, timeout=10)
        print(f"[Bark通知] 状态码: {resp.status_code}, 响应: {resp.text[:100]}")
        if resp.status_code == 200:
            return
    except Exception as e:
        print(f"[Bark通知] POST失败: {e}")
    try:
        import urllib.parse
        params = urllib.parse.urlencode({"title": title, "body": content, "group": bark_group})
        resp = requests.get(f"{url}/{title}/{content}?group={bark_group}", timeout=10)
        print(f"[Bark通知] GET状态码: {resp.status_code}, 响应: {resp.text[:100]}")
    except Exception as e:
        print(f"[Bark通知] GET失败: {e}")

def set_account_leverage(apikey, secretkey, passphrase, flag, inst_id, lever, mgn_mode="isolated"):
    """
    设置账户指定标的的杠杆倍数。
    :param apikey: API KEY
    :param secretkey: SECRET KEY
    :param passphrase: PASSPHRASE
    :param flag: "0"为实盘，"1"为模拟盘
    :param inst_id: 标的ID，如"BTC-USDT-SWAP"、"ETH-USDT-SWAP"、"BTC-USDT"等
    :param lever: 杠杆倍数，字符串类型，如"5"
    :param mgn_mode: 保证金模式，默认"isolated"（逐仓）
    :return: OKX接口返回的原始结果
    """
    accountAPI = Account.AccountAPI(apikey, secretkey, passphrase, False, flag)
    result = accountAPI.set_leverage(
        instId=inst_id,
        lever=lever,
        mgnMode=mgn_mode
    )
    return result