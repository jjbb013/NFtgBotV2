import re
import logging

logger = logging.getLogger(__name__)

CLOSE_KEYWORDS_BOTH = ['执行交易:MA止损', 'MA止损', 'MA 止损']
CLOSE_KEYWORDS_SHORT = ['空止盈', '空止损', '平空']
CLOSE_KEYWORDS_LONG = ['多止盈', '多止损', '平多']


def extract_trade_info(message):
    if any(kw in message for kw in CLOSE_KEYWORDS_BOTH + CLOSE_KEYWORDS_SHORT + CLOSE_KEYWORDS_LONG):
        return None, None

    action_pattern = r"执行交易[:：]?(.+?)(?= \d+\.\d+\w+)"
    action_match = re.search(action_pattern, message)
    symbol_pattern = r"策略当前交易对[:：]?(\w+USDT\.P)"
    symbol_match = re.search(symbol_pattern, message)

    if action_match and symbol_match:
        action_text = action_match.group(1).strip()
        symbol = symbol_match.group(1).replace('USDT.P', '')
        action = '做多' if '做多' in action_text or '买入' in action_text else '做空'
        return action, symbol

    patterns = {
        '做多': [
            r'做多\s*([A-Z]+)', r'([A-Z]+)\s*做多',
            r'买入\s*([A-Z]+)', r'([A-Z]+)\s*买入',
            r'LONG\s*([A-Z]+)', r'([A-Z]+)\s*LONG',
        ],
        '做空': [
            r'做空\s*([A-Z]+)', r'([A-Z]+)\s*做空',
            r'卖出\s*([A-Z]+)', r'([A-Z]+)\s*卖出',
            r'SHORT\s*([A-Z]+)', r'([A-Z]+)\s*SHORT',
        ],
    }
    for action, pattern_list in patterns.items():
        for pattern in pattern_list:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return action, match.group(1).upper()
    return None, None


def extract_close_signal(message):
    close_type = None
    if any(kw in message for kw in CLOSE_KEYWORDS_BOTH):
        close_type = 'both'
    elif any(kw in message for kw in CLOSE_KEYWORDS_SHORT):
        close_type = 'short'
    elif any(kw in message for kw in CLOSE_KEYWORDS_LONG):
        close_type = 'long'
    else:
        return None, None

    symbol_pattern = r"策略当前交易对[:：]?(\w+USDT\.P)"
    symbol_match = re.search(symbol_pattern, message)
    if symbol_match:
        symbol = symbol_match.group(1).upper().replace('USDT.P', '').replace('USDT', '')
        return close_type, symbol

    if close_type == 'both':
        trend_match = re.search(r"趋势策略-([A-Z]+)", message)
        if trend_match:
            return close_type, trend_match.group(1).upper()

    logger.warning(f"检测到平仓信号 ({close_type}) 但未能提取交易对。消息: {message}")
    return close_type, None
