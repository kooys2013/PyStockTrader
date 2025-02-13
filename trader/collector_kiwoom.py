import os
import sys
import time
import warnings
import pythoncom
import numpy as np
from PyQt5 import QtWidgets
from PyQt5.QAxContainer import QAxWidget
warnings.filterwarnings("ignore", category=np.VisibleDeprecationWarning)
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
from utility.static import *
from utility.setting import *


class CollectorKiwoom:
    app = QtWidgets.QApplication(sys.argv)

    def __init__(self, windowQ, collectorQ, sstgQ, soundQ, queryQ, teleQ, tick1Q):
        self.windowQ = windowQ
        self.collectorQ = collectorQ
        self.sstgQ = sstgQ
        self.soundQ = soundQ
        self.queryQ = queryQ
        self.teleQ = teleQ
        self.tick1Q = tick1Q

        self.dict_bool = {
            '실시간조건검색시작': False,
            '실시간조건검색중단': False,

            '로그인': False,
            'TR수신': False,
            'TR다음': False,
            'CD수신': False,
            'CR수신': False
        }
        self.dict_gsjm = {}
        self.dict_vipr = {}
        self.dict_tick = {}
        self.dict_hoga = {}
        self.dict_cond = {}
        self.name_code = {}

        self.list_gsjm = []
        self.list_trcd = []
        self.list_jang = []
        self.list_code = None
        self.list_kosd = None

        self.df_tr = None
        self.dict_item = None
        self.str_trname = None

        self.operation = 1
        self.df_mt = pd.DataFrame(columns=['거래대금상위100'])
        self.str_tday = strf_time('%Y%m%d')
        self.str_jcct = self.str_tday + '090000'

        remaintime = (strp_time('%Y%m%d%H%M%S', self.str_tday + '090100') - now()).total_seconds()
        exittime = timedelta_sec(remaintime) if remaintime > 0 else timedelta_sec(600)
        self.exit_time = exittime
        self.time_mtop = now()

        self.ocx = QAxWidget('KHOPENAPI.KHOpenAPICtrl.1')
        self.ocx.OnEventConnect.connect(self.OnEventConnect)
        self.ocx.OnReceiveTrData.connect(self.OnReceiveTrData)
        self.ocx.OnReceiveRealData.connect(self.OnReceiveRealData)
        self.ocx.OnReceiveTrCondition.connect(self.OnReceiveTrCondition)
        self.ocx.OnReceiveConditionVer.connect(self.OnReceiveConditionVer)
        self.ocx.OnReceiveRealCondition.connect(self.OnReceiveRealCondition)
        self.Start()

    def Start(self):
        self.CommConnect()
        self.EventLoop()

    def CommConnect(self):
        self.ocx.dynamicCall('CommConnect()')
        while not self.dict_bool['로그인']:
            pythoncom.PumpWaitingMessages()

        self.dict_bool['CD수신'] = False
        self.ocx.dynamicCall('GetConditionLoad()')
        while not self.dict_bool['CD수신']:
            pythoncom.PumpWaitingMessages()

        self.list_kosd = self.GetCodeListByMarket('10')
        list_code = self.GetCodeListByMarket('0') + self.list_kosd
        df = pd.DataFrame(columns=['종목명'])
        for code in list_code:
            name = self.GetMasterCodeName(code)
            df.at[code] = name
            self.name_code[name] = code

        self.queryQ.put([3, df, 'codename', 'replace'])

        data = self.ocx.dynamicCall('GetConditionNameList()')
        conditions = data.split(';')[:-1]
        for condition in conditions:
            cond_index, cond_name = condition.split('^')
            self.dict_cond[int(cond_index)] = cond_name

        self.windowQ.put([ui_num['S단순텍스트'], '시스템 명령 실행 알림 - OpenAPI 로그인 완료'])

    def EventLoop(self):
        self.OperationRealreg()
        self.ViRealreg()
        while True:
            if not self.collectorQ.empty():
                work = self.collectorQ.get()
                if type(work) == list:
                    self.UpdateRealreg(work)
                elif type(work) == str:
                    self.UpdateJangolist(work)
                continue

            if self.operation == 1 and now() > self.exit_time:
                break

            if self.operation == 3:
                if not self.dict_bool['실시간조건검색시작']:
                    self.ConditionSearchStart()
            if self.operation == 2:
                if not self.dict_bool['실시간조건검색중단']:
                    self.ConditionSearchStop()
            if self.operation == 8:
                self.AllRemoveRealreg()
                self.SaveDatabase()
                break

            if now() > self.time_mtop:
                if len(self.df_mt) > 0:
                    self.UpdateMoneyTop()
                self.time_mtop = timedelta_sec(+1)

            time_loop = timedelta_sec(0.25)
            while now() < time_loop:
                pythoncom.PumpWaitingMessages()
                time.sleep(0.0001)

        self.windowQ.put([ui_num['S단순텍스트'], '시스템 명령 실행 알림 - 콜렉터를 종료합니다.'])
        if DICT_SET['알림소리1']:
            self.soundQ.put('주식 콜렉터를 종료합니다.')
        self.teleQ.put('주식 콜렉터를 종료하였습니다.')
        sys.exit()

    def UpdateRealreg(self, rreg):
        sn = rreg[0]
        if len(rreg) == 2:
            self.ocx.dynamicCall('SetRealRemove(QString, QString)', rreg)
            self.windowQ.put([ui_num['S단순텍스트'], f'실시간 알림 중단 완료 - 모든 실시간 데이터 수신 중단'])
        elif len(rreg) == 4:
            ret = self.ocx.dynamicCall('SetRealReg(QString, QString, QString, QString)', rreg)
            result = '완료' if ret == 0 else '실패'
            if sn == sn_oper:
                self.windowQ.put([ui_num['S단순텍스트'], f'실시간 알림 등록 {result} - 장운영시간 [{sn}]'])
            else:
                text = f"실시간 알림 등록 {result} - [{sn}] 종목갯수 {len(rreg[1].split(';'))}"
                self.windowQ.put([ui_num['S단순텍스트'], text])

    def UpdateJangolist(self, work):
        code = work.split(' ')[1]
        if '잔고편입' in work and code not in self.list_jang:
            self.list_jang.append(code)
        elif '잔고청산' in work and code in self.list_jang:
            self.list_jang.remove(code)
            if code not in self.list_gsjm and code in self.dict_gsjm.keys():
                self.sstgQ.put(['조건이탈', code])
                del self.dict_gsjm[code]

    def OperationRealreg(self):
        self.collectorQ.put([sn_oper, ' ', '215;20;214', 0])
        self.list_code = self.SendCondition(sn_oper, self.dict_cond[1], 1, 0)
        k = 0
        for i in range(0, len(self.list_code), 100):
            self.collectorQ.put([sn_jchj + k, ';'.join(self.list_code[i:i + 100]), '10;12;14;30;228;41;61;71;81', 1])
            k += 1
        self.windowQ.put([ui_num['S단순텍스트'], '시스템 명령 실행 알림 - 장운영시간 등록 완료'])

    def ViRealreg(self):
        self.Block_Request('opt10054', 시장구분='000', 장전구분='1', 종목코드='', 발동구분='1', 제외종목='111111011',
                           거래량구분='0', 거래대금구분='0', 발동방향='0', output='발동종목', next=0)
        self.windowQ.put([ui_num['S단순텍스트'], '시스템 명령 실행 알림 - VI발동해제 등록 완료'])
        self.windowQ.put([ui_num['S단순텍스트'], '시스템 명령 실행 알림 - 시스템 시작 완료'])

    def ConditionSearchStart(self):
        self.dict_bool['실시간조건검색시작'] = True
        codes = self.SendCondition(sn_cond, self.dict_cond[0], 0, 1)
        self.df_mt.at[self.str_tday + '090000'] = ';'.join(codes)
        if len(codes) > 0:
            for code in codes:
                self.list_gsjm.append(code)
                self.dict_gsjm[code] = '090000'
                self.sstgQ.put(['조건진입', code])
        self.windowQ.put([ui_num['S단순텍스트'], '시스템 명령 실행 알림 - 실시간조건검색 등록 완료'])

    def ConditionSearchStop(self):
        self.dict_bool['실시간조건검색중단'] = True
        self.ocx.dynamicCall("SendConditionStop(QString, QString, int)", sn_cond, self.dict_cond[0], 0)

    def AllRemoveRealreg(self):
        self.collectorQ.put(['ALL', 'ALL'])
        self.windowQ.put([ui_num['S단순텍스트'], '시스템 명령 실행 알림 - 실시간 데이터 중단 완료'])

    def SaveDatabase(self):
        self.queryQ.put([3, self.df_mt, 'moneytop', 'append'])
        con = sqlite3.connect(DB_TRADELIST)
        df = pd.read_sql(f"SELECT * FROM s_tradelist WHERE 체결시간 LIKE '{self.str_tday}%'", con)
        con.close()
        df = df.set_index('index')
        codes = []
        for index in df.index:
            code = self.name_code[df['종목명'][index]]
            if code not in codes:
                codes.append(code)
        self.tick1Q.put(['틱데이터저장', codes])

    def UpdateMoneyTop(self):
        timetype = '%Y%m%d%H%M%S'
        list_text = ';'.join(self.list_gsjm)
        curr_datetime = strp_time(timetype, self.str_jcct)
        last_datetime = strp_time(timetype, self.df_mt.index[-1])
        gap_seconds = (curr_datetime - last_datetime).total_seconds()
        pre_time2 = strf_time(timetype, timedelta_sec(-2, curr_datetime))
        pre_time1 = strf_time(timetype, timedelta_sec(-1, curr_datetime))
        if 1 <= gap_seconds < 2:
            self.df_mt.at[pre_time1] = list_text
        elif 2 <= gap_seconds < 3:
            self.df_mt.at[pre_time2] = list_text
            self.df_mt.at[pre_time1] = list_text
        self.df_mt.at[self.str_jcct] = list_text

    def OnEventConnect(self, err_code):
        if err_code == 0:
            self.dict_bool['로그인'] = True

    def OnReceiveConditionVer(self, ret, msg):
        if msg == '':
            return
        if ret == 1:
            self.dict_bool['CD수신'] = True

    def OnReceiveTrCondition(self, screen, code_list, cond_name, cond_index, nnext):
        if screen == "" and cond_name == "" and cond_index == "" and nnext == "":
            return
        codes = code_list.split(';')[:-1]
        self.list_trcd = codes
        self.dict_bool['CR수신'] = True

    def OnReceiveRealCondition(self, code, IorD, cname):
        if cname == "":
            return

        if IorD == 'I':
            if code not in self.list_gsjm:
                self.list_gsjm.append(code)
            if code not in self.list_jang and code not in self.dict_gsjm.keys():
                self.sstgQ.put(['조건진입', code])
                self.dict_gsjm[code] = '090000'
        elif IorD == 'D':
            if code in self.list_gsjm:
                self.list_gsjm.remove(code)
            if code not in self.list_jang and code in self.dict_gsjm.keys():
                self.sstgQ.put(['조건이탈', code])
                del self.dict_gsjm[code]

    def OnReceiveRealData(self, code, realtype, realdata):
        if realdata == '':
            return

        if realtype == '장시작시간':
            try:
                self.operation = int(self.GetCommRealData(code, 215))
                current = self.GetCommRealData(code, 20)
                remain = self.GetCommRealData(code, 214)
            except Exception as e:
                self.windowQ.put([1, f'OnReceiveRealData 장시작시간 {e}'])
            else:
                self.windowQ.put([1, f'장운영 시간 수신 알림 - {self.operation} {current[:2]}:{current[2:4]}:{current[4:]} '
                                     f'남은시간 {remain[:2]}:{remain[2:4]}:{remain[4:]}'])
        elif realtype == 'VI발동/해제':
            try:
                code = self.GetCommRealData(code, 9001).strip('A').strip('Q')
                gubun = self.GetCommRealData(code, 9068)
                name = self.GetMasterCodeName(code)
            except Exception as e:
                self.windowQ.put([ui_num['S단순텍스트'], f'OnReceiveRealData VI발동/해제 {e}'])
            else:
                if gubun == '1' and code in self.list_code and \
                        (code not in self.dict_vipr.keys() or
                         (self.dict_vipr[code][0] and now() > self.dict_vipr[code][1])):
                    self.UpdateViPriceDown5(code, name)
        elif realtype == '주식체결':
            try:
                c = abs(int(self.GetCommRealData(code, 10)))
                o = abs(int(self.GetCommRealData(code, 16)))
                v = int(self.GetCommRealData(code, 15))
                t = self.GetCommRealData(code, 20)
            except Exception as e:
                self.windowQ.put([ui_num['S단순텍스트'], f'OnReceiveRealData 주식체결 {e}'])
            else:
                if self.operation == 1:
                    self.operation = 3
                if t != self.str_jcct[8:]:
                    self.str_jcct = self.str_tday + t
                if code not in self.dict_vipr.keys():
                    self.InsertViPriceDown5(code, o)
                if code in self.dict_vipr.keys() and not self.dict_vipr[code][0] and now() > self.dict_vipr[code][1]:
                    self.UpdateViPriceDown5(code, c)
                try:
                    pret = self.dict_tick[code][0]
                    bid_volumns = self.dict_tick[code][1]
                    ask_volumns = self.dict_tick[code][2]
                except KeyError:
                    pret = None
                    bid_volumns = 0
                    ask_volumns = 0
                if v > 0:
                    self.dict_tick[code] = [t, bid_volumns + abs(v), ask_volumns]
                else:
                    self.dict_tick[code] = [t, bid_volumns, ask_volumns + abs(v)]
                if t != pret:
                    bids = self.dict_tick[code][1]
                    asks = self.dict_tick[code][2]
                    self.dict_tick[code] = [t, 0, 0]
                    try:
                        h = abs(int(self.GetCommRealData(code, 17)))
                        low = abs(int(self.GetCommRealData(code, 18)))
                        per = float(self.GetCommRealData(code, 12))
                        dm = int(self.GetCommRealData(code, 14))
                        ch = float(self.GetCommRealData(code, 228))
                        vp = abs(float(self.GetCommRealData(code, 30)))
                        name = self.GetMasterCodeName(code)
                    except Exception as e:
                        self.windowQ.put([ui_num['S단순텍스트'], f'OnReceiveRealData 주식체결 {e}'])
                    else:
                        self.UpdateTickData(code, name, c, o, h, low, per, dm, ch, vp, bids, asks, t, now())
        elif realtype == '주식호가잔량':
            try:
                s2hg = abs(int(self.GetCommRealData(code, 42)))
                s1hg = abs(int(self.GetCommRealData(code, 41)))
                b1hg = abs(int(self.GetCommRealData(code, 51)))
                b2hg = abs(int(self.GetCommRealData(code, 52)))
                s2jr = int(self.GetCommRealData(code, 62))
                s1jr = int(self.GetCommRealData(code, 61))
                b1jr = int(self.GetCommRealData(code, 71))
                b2jr = int(self.GetCommRealData(code, 72))
            except Exception as e:
                self.windowQ.put([ui_num['S단순텍스트'], f'OnReceiveRealData 주식호가잔량 {e}'])
            else:
                self.dict_hoga[code] = [s2hg, s1hg, b1hg, b2hg, s2jr, s1jr, b1jr, b2jr]

    def InsertViPriceDown5(self, code, o):
        vid5 = self.GetVIPriceDown5(code, o)
        self.dict_vipr[code] = [True, timedelta_sec(-180), vid5]

    def GetVIPriceDown5(self, code, std_price):
        vi = std_price * 1.1
        x = self.GetHogaunit(code, vi)
        if vi % x != 0:
            vi = vi + (x - vi % x)
        return int(vi - x * 5)

    def GetHogaunit(self, code, price):
        if price < 1000:
            x = 1
        elif 1000 <= price < 5000:
            x = 5
        elif 5000 <= price < 10000:
            x = 10
        elif 10000 <= price < 50000:
            x = 50
        elif code in self.list_kosd:
            x = 100
        elif 50000 <= price < 100000:
            x = 100
        elif 100000 <= price < 500000:
            x = 500
        else:
            x = 1000
        return x

    def UpdateViPriceDown5(self, code, key):
        if type(key) == str:
            if code in self.dict_vipr.keys():
                self.dict_vipr[code][0] = False
                self.dict_vipr[code][1] = timedelta_sec(5)
            else:
                self.dict_vipr[code] = [False, timedelta_sec(5), 0]
            self.windowQ.put([ui_num['S단순텍스트'], f'변동성 완화 장치 발동 - [{code}] {key}'])
        elif type(key) == int:
            vid5 = self.GetVIPriceDown5(code, key)
            self.dict_vipr[code] = [True, timedelta_sec(5), vid5]

    def UpdateTickData(self, code, name, c, o, h, low, per, dm, ch, vp, bids, asks, t, receivetime):
        if DICT_SET['키움트레이더'] and code in self.dict_gsjm.keys():
            injango = code in self.list_jang
            vitimedown = now() < timedelta_sec(180, self.dict_vipr[code][1])
            vid5priceup = c >= self.dict_vipr[code][2]
            self.sstgQ.put([code, name, c, o, h, low, per, ch, dm, t, injango, vitimedown, vid5priceup, receivetime])

        vitime = strf_time('%Y%m%d%H%M%S', self.dict_vipr[code][1])
        vid5 = self.dict_vipr[code][2]
        try:
            s2hg, s1hg, b1hg, b2hg, s2jr, s1jr, b1jr, b2jr = self.dict_hoga[code]
        except KeyError:
            s2hg, s1hg, b1hg, b2hg, s2jr, s1jr, b1jr, b2jr = 0, 0, 0, 0, 0, 0, 0, 0
        self.tick1Q.put([code, c, o, h, low, per, dm, ch, vp, bids, asks, vitime, vid5,
                         s2hg, s1hg, b1hg, b2hg, s2jr, s1jr, b1jr, b2jr, t, receivetime])

    def OnReceiveTrData(self, screen, rqname, trcode, record, nnext):
        if screen == '' and record == '':
            return
        items = None
        self.dict_bool['TR다음'] = True if nnext == '2' else False
        for output in self.dict_item['output']:
            record = list(output.keys())[0]
            items = list(output.values())[0]
            if record == self.str_trname:
                break
        rows = self.ocx.dynamicCall('GetRepeatCnt(QString, QString)', trcode, rqname)
        if rows == 0:
            rows = 1
        df2 = []
        for row in range(rows):
            row_data = []
            for item in items:
                data = self.ocx.dynamicCall('GetCommData(QString, QString, int, QString)', trcode, rqname, row, item)
                row_data.append(data.strip())
            df2.append(row_data)
        df = pd.DataFrame(data=df2, columns=items)
        self.df_tr = df
        self.dict_bool['TR수신'] = True

    def Block_Request(self, *args, **kwargs):
        trcode = args[0].lower()
        lines = readEnc(trcode)
        self.dict_item = parseDat(trcode, lines)
        self.str_trname = kwargs['output']
        nnext = kwargs['next']
        for i in kwargs:
            if i.lower() != 'output' and i.lower() != 'next':
                self.ocx.dynamicCall('SetInputValue(QString, QString)', i, kwargs[i])
        self.dict_bool['TR수신'] = False
        self.dict_bool['TR다음'] = False
        self.ocx.dynamicCall('CommRqData(QString, QString, int, QString)', self.str_trname, trcode, nnext, sn_brrq)
        sleeptime = timedelta_sec(0.25)
        while not self.dict_bool['TR수신'] or now() < sleeptime:
            pythoncom.PumpWaitingMessages()
        return self.df_tr

    def SendCondition(self, screen, cond_name, cond_index, search):
        self.dict_bool['CR수신'] = False
        self.ocx.dynamicCall('SendCondition(QString, QString, int, int)', screen, cond_name, cond_index, search)
        while not self.dict_bool['CR수신']:
            pythoncom.PumpWaitingMessages()
        return self.list_trcd

    def GetMasterCodeName(self, code):
        return self.ocx.dynamicCall('GetMasterCodeName(QString)', code)

    def GetCodeListByMarket(self, market):
        data = self.ocx.dynamicCall('GetCodeListByMarket(QString)', market)
        tokens = data.split(';')[:-1]
        return tokens

    def GetCommRealData(self, code, fid):
        return self.ocx.dynamicCall('GetCommRealData(QString, int)', code, fid)
