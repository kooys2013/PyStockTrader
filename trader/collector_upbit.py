import os
import sys
import pyupbit
from PyQt5.QtCore import QThread
from pyupbit import WebSocketManager
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
from utility.static import now


class WebsTicker(QThread):
    def __init__(self, tick2Q):
        super().__init__()
        self.tick2Q = tick2Q

    def run(self):
        dict_askbid = {}
        tickers = pyupbit.get_tickers(fiat="KRW")
        websQ_ticker = WebSocketManager('ticker', tickers)
        while True:
            data = websQ_ticker.get()
            ticker = data['code']
            t = data['trade_time']
            v = data['trade_volume']
            ask_bid = data['ask_bid']
            try:
                pret = dict_askbid[ticker][0]
                bid_volumns = dict_askbid[ticker][1]
                ask_volumns = dict_askbid[ticker][2]
            except KeyError:
                pret = None
                bid_volumns = 0
                ask_volumns = 0
            if ask_bid == 'BID':
                dict_askbid[ticker] = [t, bid_volumns + float(v), ask_volumns]
            else:
                dict_askbid[ticker] = [t, bid_volumns, ask_volumns + float(v)]
            if t != pret:
                data['매수수량'] = dict_askbid[ticker][1]
                data['매도수량'] = dict_askbid[ticker][2]
                dict_askbid[ticker] = [t, 0, 0]
                self.tick2Q.put([data, now()])


class WebsOrderbook(QThread):
    def __init__(self, tick2Q):
        super().__init__()
        self.tick2Q = tick2Q

    def run(self):
        tickers = pyupbit.get_tickers(fiat="KRW")
        websQ_order = WebSocketManager('orderbook', tickers)
        while True:
            data = websQ_order.get()
            self.tick2Q.put(data)
