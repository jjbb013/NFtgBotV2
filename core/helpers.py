import os
import random
import string
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
