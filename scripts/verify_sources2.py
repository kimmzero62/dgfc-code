"""2차 검증: 1차에서 실패한 소스의 대체 경로를 확인한다."""
from __future__ import annotations

import io
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}


def show(label, fn):
    t0 = time.time()
    try:
        out = fn()
    except Exception as e:  # noqa: BLE001
        out = f"FAIL {type(e).__name__}: {str(e)[:300]}"
    print(f"### {label} ({time.time() - t0:.1f}s)\n{out}\n", flush=True)


def kofia(scheme):
    def _f():
        end = date.today()
        start = end - timedelta(days=400)
        body = ('<?xml version="1.0" encoding="utf-8"?><message><proframeHeader><pfmAppName>BIS-KOFIABOND</pfmAppName>'
                '<pfmSvcName>BISLastAskPrcROPSrchSO</pfmSvcName><pfmFnName>listTrm</pfmFnName></proframeHeader>'
                '<systemHeader></systemHeader><BISComDspDatDTO><val1>DD</val1>'
                f'<val2>{start:%Y%m%d}</val2><val3>{end:%Y%m%d}</val3><val4>1530</val4>'
                '<val5>3009</val5><val6>3010</val6><val7>4000</val7></BISComDspDatDTO></message>')
        r = requests.post(f"{scheme}://www.kofiabond.or.kr/proframeWeb/XMLSERVICES/", data=body.encode(),
                          headers={**UA, "Content-Type": "text/xml; charset=utf-8"}, timeout=60)
        txt = r.content.decode("utf-8", errors="replace")
        rows = []
        try:
            root = ET.fromstring(txt)
            for d in root.iter("BISComDspDatDTO"):
                rows.append([(d.find(f"val{i}").text if d.find(f"val{i}") is not None else None) for i in range(1, 5)])
        except ET.ParseError as e:
            return f"HTTP {r.status_code} parse error {e}; head={txt[:400]!r}"
        return f"HTTP {r.status_code} rows={len(rows)} first={rows[:3]} last={rows[-3:]}"
    return _f


def fred_slow():
    r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A3HYC", headers=UA, timeout=(20, 150))
    lines = r.text.splitlines()
    return f"HTTP {r.status_code} lines={len(lines)} last={lines[-2:]}"


def fred_api_nokey():
    r = requests.get("https://api.stlouisfed.org/fred/series/observations?series_id=DGS30&file_type=json", timeout=30)
    return f"HTTP {r.status_code} body={r.text[:200]!r}"


def get(url, **kw):
    def _f():
        r = requests.get(url, headers={**UA, **kw.pop("headers", {})}, timeout=30, **kw)
        return f"HTTP {r.status_code} ct={r.headers.get('content-type')} body={r.text[:500]!r}"
    return _f


def krx_direct():
    end = date.today()
    r = requests.post("https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd",
                      data={"bld": "dbms/MDC/STAT/standard/MDCSTAT02201", "locale": "ko_KR", "inqTpCd": "2",
                            "trdVolVal": "2", "askBid": "3", "mktId": "STK",
                            "strtDd": f"{end - timedelta(days=14):%Y%m%d}", "endDd": f"{end:%Y%m%d}",
                            "detailView": "1", "money": "3"},
                      headers={**UA, "Referer": "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd"},
                      timeout=30)
    return f"HTTP {r.status_code} body={r.text[:400]!r}"


show("KOFIA https", kofia("https"))
show("KOFIA http", kofia("http"))
show("FRED fredgraph 150s", fred_slow)
show("FRED API (키 없이, 400이면 호스트 접근은 가능)", fred_api_nokey)
show("ECOS sample 10건", get("https://ecos.bok.or.kr/api/StatisticItemList/sample/json/kr/1/10/817Y002"))
show("KRX 직접", krx_direct)
show("Naver mobile index trend", get("https://m.stock.naver.com/api/index/KOSPI/trend"))
show("Naver mobile investor", get("https://m.stock.naver.com/api/index/KOSPI/investorTrend?pageSize=10&page=1"))
show("Naver front-api deal trend", get("https://m.stock.naver.com/front-api/marketIndex/investorDealTrend?category=KOSPI"))
show("Naver PC 투자자 일별(sise_trans_style)", get("https://finance.naver.com/sise/sise_trans_style.naver?sosok=01"))
show("Daum investors", get("https://finance.daum.net/api/investor/days?market=KOSPI&page=1&perPage=10",
                           headers={"Referer": "https://finance.daum.net/domestic/investors"}))
