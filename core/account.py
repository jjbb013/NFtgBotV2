import json
import logging

import okx.Account as Account
import okx.MarketData as MarketData
import okx.Trade as Trade

from core.helpers import build_order_params

logger = logging.getLogger(__name__)


class OKXAccount:
    def __init__(self, config):
        self.cfg = config
        self.idx = config['account_idx']
        self.name = config['account_name']
        self.flag = config['FLAG']
        key = config['API_KEY']
        secret = config['SECRET_KEY']
        passphrase = config['PASSPHRASE']
        self.trade_api = Trade.TradeAPI(key, secret, passphrase, False, self.flag)
        self.account_api = Account.AccountAPI(key, secret, passphrase, False, self.flag)
        self.market_api = MarketData.MarketAPI(flag=self.flag, debug=False)

    def _inst_id(self, symbol):
        return f"{symbol.upper()}-USDT-SWAP"

    def get_price(self, symbol):
        try:
            inst_id = self._inst_id(symbol)
            resp = self.market_api.get_ticker(instId=inst_id)
            if resp.get('code') == '0' and resp.get('data'):
                return float(resp['data'][0]['last'])
            logger.error(f"[{self.name}] 获取 {symbol} 价格失败: {resp.get('msg')}")
        except Exception as e:
            logger.error(f"[{self.name}] 获取 {symbol} 价格异常: {e}")
        return None

    def get_balance(self):
        try:
            resp = self.account_api.get_account_balance()
            if resp.get('code') == '0':
                for detail in resp['data'][0].get('details', []):
                    if detail.get('ccy') == 'USDT':
                        return float(detail.get('availEq', 0))
            logger.error(f"[{self.name}] 获取余额失败: {resp.get('msg')}")
        except Exception as e:
            logger.error(f"[{self.name}] 获取余额异常: {e}")
        return None

    def place_order(self, action, symbol, size):
        try:
            price = self.get_price(symbol)
            if not price:
                return {"success": False, "error_msg": "无法获取市场价格"}

            tp_ratio = self.cfg['TP_RATIO']
            sl_ratio = self.cfg['SL_RATIO']
            leverage = self.cfg['LEVERAGE']

            side, pos_side = ('buy', 'long') if action == '做多' else ('sell', 'short')
            tp_price = price * (1 + (tp_ratio if side == 'buy' else -tp_ratio))
            sl_price = price * (1 - (sl_ratio if side == 'buy' else -sl_ratio))
            tp_price = round(tp_price, 4)
            sl_price = round(sl_price, 4)

            params = build_order_params(
                self._inst_id(symbol), side, price, size, pos_side, tp_price, sl_price
            )
            logger.info(f"[{self.name}] 下单参数: {json.dumps(params, ensure_ascii=False)}")
            resp = self.trade_api.place_order(**params)
            logger.info(f"[{self.name}] 下单返回: {json.dumps(resp, ensure_ascii=False)}")

            if resp.get('code') == '0' and resp.get('data') and resp['data'][0].get('sCode') == '0':
                margin = round(price * size / leverage, 4)
                return {
                    "success": True,
                    "market_price": price,
                    "margin": margin,
                    "take_profit": tp_price,
                    "stop_loss": sl_price,
                    "clOrdId": params['clOrdId'],
                    "okx_resp": resp,
                }
            return {"success": False, "error_msg": resp['data'][0].get('sMsg', '未知错误'), "okx_resp": resp}
        except Exception as e:
            logger.error(f"[{self.name}] 下单异常: {e}")
            return {"success": False, "error_msg": str(e)}

    def close_positions(self, symbol, close_type):
        try:
            inst_id = self._inst_id(symbol)
            resp = self.account_api.get_positions(instId=inst_id)
            if resp.get('code') != '0':
                return {"success": False, "error_msg": f"获取持仓失败: {resp.get('msg')}"}

            positions = []
            if close_type == 'both':
                positions = [p for p in resp.get('data', []) if float(p.get('pos', '0')) > 0]
            else:
                positions = [
                    p for p in resp.get('data', [])
                    if float(p.get('pos', '0')) > 0 and p.get('posSide') == close_type
                ]

            if not positions:
                return {"success": True, "close_results": [], "message": "没有可平仓位"}

            results = []
            for pos in positions:
                pos_side = pos.get('posSide')
                side = 'sell' if pos_side == 'long' else 'buy'
                close_resp = self.trade_api.place_order(
                    instId=inst_id,
                    tdMode='cross',
                    side=side,
                    posSide=pos_side,
                    ordType='market',
                    sz=pos['pos'],
                )
                if close_resp.get('code') == '0' and close_resp['data'][0].get('sCode') == '0':
                    results.append({
                        'pos_side': pos_side,
                        'size': pos['pos'],
                        'order_id': close_resp['data'][0]['ordId'],
                    })
                else:
                    results.append({
                        'pos_side': pos_side,
                        'size': pos['pos'],
                        'error_msg': close_resp['data'][0].get('sMsg', '未知错误'),
                    })
            return {"success": True, "close_results": results, "okx_resp": resp}
        except Exception as e:
            logger.error(f"[{self.name}] 平仓异常: {e}")
            return {"success": False, "error_msg": str(e)}

    def get_orders(self, symbol, limit=10):
        try:
            inst_id = self._inst_id(symbol)
            resp = self.trade_api.get_orders_history(
                instType='SWAP',
                instId=inst_id,
                limit=str(limit),
            )
            if resp.get('code') == '0':
                return resp.get('data', [])
            logger.error(f"[{self.name}] 获取订单历史失败: {resp.get('msg')}")
        except Exception as e:
            logger.error(f"[{self.name}] 获取订单历史异常: {e}")
        return []

    def set_leverage(self, symbol, leverage):
        try:
            inst_id = self._inst_id(symbol)
            resp = self.account_api.set_leverage(
                instId=inst_id,
                lever=str(leverage),
                mgnMode='cross',
            )
            msg = resp.get('msg', '成功') if resp.get('code') == '0' else str(resp)
            log = f"[{self.name}] {inst_id} 杠杆设置为 {leverage}x (cross) - {msg}"
            logger.info(log)
            return log
        except Exception as e:
            logger.error(f"[{self.name}] {symbol} 杠杆设置异常: {e}")
            return f"[{self.name}] {symbol} 杠杆设置异常: {e}"
