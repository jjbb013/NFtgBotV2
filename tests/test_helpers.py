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
