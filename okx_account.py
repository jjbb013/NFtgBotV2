import os
import logging
import json
from utils import get_shanghai_time, generate_clord_id
import okx.Trade as Trade
import okx.MarketData as MarketData
import okx.Account as Account

logger = logging.getLogger(__name__)

class OKXAccount:
    def __init__(self, account_config):
        self.config = account_config
        self.name = account_config['account_name']
        self.idx = account_config['account_idx']
        self.flag = account_config['FLAG']
        
        api_key = account_config['API_KEY']
        secret_key = account_config['SECRET_KEY']
        passphrase = account_config['PASSPHRASE']
        
        self.trade_api = Trade.TradeAPI(api_key, secret_key, passphrase, False, self.flag)
        self.account_api = Account.AccountAPI(api_key, secret_key, passphrase, False, self.flag)
        self.market_api = MarketData.MarketAPI(flag=self.flag, debug=False)

    def get_order_size(self, symbol):
        coin = symbol.split('-')[0]
        val = os.getenv(f"OKX{self.idx}_FIXED_QTY_{coin}")
        return float(val) if val else None

    def get_latest_market_price(self, symbol):
        try:
            inst_id = f"{symbol.upper()}-USDT-SWAP"
            response = self.market_api.get_ticker(instId=inst_id)
            if response['code'] == '0' and response['data']:
                return float(response['data'][0]['last'])
            logger.error(f"[{self.name}] 获取 {symbol} 价格失败: {response.get('msg', '未知错误')}")
        except Exception as e:
            logger.error(f"[{self.name}] 获取 {symbol} 价格异常: {e}")
        return None

    async def place_order(self, action, symbol, size):
        try:
            price = self.get_latest_market_price(symbol)
            if not price:
                return {"success": False, "error_msg": "无法获取市场价格"}

            tp_ratio = float(os.getenv(f"OKX{self.idx}_TP_RATIO", '0.01'))
            sl_ratio = float(os.getenv(f"OKX{self.idx}_SL_RATIO", '0.027'))
            leverage = int(os.getenv(f"OKX{self.idx}_LEVERAGE", 10))

            side, pos_side = ('buy', 'long') if action == '做多' else ('sell', 'short')
            tp_price = price * (1 + (tp_ratio if side == 'buy' else -tp_ratio))
            sl_price = price * (1 - (sl_ratio if side == 'buy' else -sl_ratio))

            cl_ord_id = generate_clord_id("ORD")
            attach_algo_ord = {
                "attachAlgoClOrdId": generate_clord_id("ATTACH"),
                "tpTriggerPx": str(round(tp_price, 4)),
                "tpOrdPx": "-1",
                "tpOrdKind": "condition",
                "slTriggerPx": str(round(sl_price, 4)),
                "slOrdPx": "-1",
                "tpTriggerPxType": "last",
                "slTriggerPxType": "last"
            }
            params = {
                "instId": f"{symbol}-USDT-SWAP",
                "tdMode": "cross",
                "side": side,
                "ordType": "market",
                "sz": str(size),
                "clOrdId": cl_ord_id,
                "posSide": pos_side,
                "attachAlgoOrds": [attach_algo_ord]
            }
            logger.info(f"[{self.name}] 下单参数: {json.dumps(params, indent=2)}")
            resp = self.trade_api.place_order(**params)
            logger.info(f"[{self.name}] 下单返回: {json.dumps(resp, indent=2)}")

            if resp['code'] == '0' and resp['data'][0]['sCode'] == '0':
                return {
                    "success": True, "market_price": price, 
                    "margin": round(price * size / leverage, 4), 
                    "take_profit": tp_price, "stop_loss": sl_price, 
                    "clOrdId": params['clOrdId'], "okx_resp": resp
                }
            else:
                return {"success": False, "error_msg": resp['data'][0]['sMsg'], "okx_resp": resp}
        except Exception as e:
            logger.error(f"[{self.name}] 下单异常: {e}")
            return {"success": False, "error_msg": str(e)}

    async def close_positions(self, symbol, close_type):
        try:
            inst_id = f"{symbol.upper()}-USDT-SWAP"
            resp = self.account_api.get_positions(instId=inst_id)
            if resp['code'] != '0':
                return {"success": False, "error_msg": f"获取持仓失败: {resp.get('msg')}"}

            results = []
            positions_to_close = [
                pos for pos in resp.get('data', []) 
                if float(pos.get('pos', '0')) > 0 and pos.get('posSide') == close_type
            ]

            if not positions_to_close:
                logger.info(f"[{self.name}] 未找到 {symbol} 的 {close_type} 方向持仓可供平仓。")
                return {"success": True, "close_results": [], "message": "没有找到可平仓位"}

            for pos in positions_to_close:
                side = 'sell' if close_type == 'long' else 'buy'
                close_resp = self.trade_api.place_order(
                    instId=inst_id, tdMode='cross', side=side, 
                    posSide=close_type, ordType='market', sz=pos['pos']
                )
                if close_resp['code'] == '0' and close_resp['data'][0]['sCode'] == '0':
                    results.append({
                        'pos_side': close_type, 'size': pos['pos'], 
                        'order_id': close_resp['data'][0]['ordId']
                    })
            
            return {"success": True, "close_results": results, "okx_resp": resp}
        except Exception as e:
            logger.error(f"[{self.name}] 平仓异常: {e}")
            return {"success": False, "error_msg": str(e)}

    async def set_leverage(self, symbol, leverage, mgn_mode="cross"):
        try:
            inst_id = f"{symbol}-USDT-SWAP"
            result = self.account_api.set_leverage(
                instId=inst_id,
                lever=str(leverage),
                mgnMode=mgn_mode
            )
            log_msg = f"[{self.name}] {inst_id} 杠杆设置为 {leverage}x ({mgn_mode}) - 结果: {result.get('msg', '成功') if result.get('code') == '0' else result}"
            logger.info(log_msg)
            return log_msg
        except Exception as e:
            error_msg = f"[{self.name}] {symbol} 杠杆设置异常: {e}"
            logger.error(error_msg)
            return error_msg
