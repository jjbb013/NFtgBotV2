import pytest
from core.signals import extract_trade_info, extract_close_signal


def test_extract_long_btc():
    action, symbol = extract_trade_info("做多 BTC")
    assert action == '做多'
    assert symbol == 'BTC'


def test_extract_short_eth():
    action, symbol = extract_trade_info("ETH 做空")
    assert action == '做空'
    assert symbol == 'ETH'


def test_extract_formatted_signal():
    msg = "执行交易:做多 123.45USDT 策略当前交易对:BTCUSDT.P"
    action, symbol = extract_trade_info(msg)
    assert action == '做多'
    assert symbol == 'BTC'


def test_extract_long_ignores_close():
    assert extract_trade_info("平空 BTC") == (None, None)


def test_close_long():
    close_type, symbol = extract_close_signal("策略当前交易对:BTCUSDT.P 多止盈")
    assert close_type == 'long'
    assert symbol == 'BTC'


def test_close_both_ma():
    close_type, symbol = extract_close_signal("趋势策略-ETH MA止损")
    assert close_type == 'both'
    assert symbol == 'ETH'
