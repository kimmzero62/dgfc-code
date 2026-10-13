"""금융투자협회 채권정보센터 최종호가수익률 (로그인·키 불필요).

코드: 3009 회사채 무보증 3년 AA-, 3010 회사채 무보증 3년 BBB-, 4000 CD 91일
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date, timedelta
from functools import lru_cache

import pandas as pd

from ._http import clean, request

URL = "https://www.kofiabond.or.kr/proframeWeb/XMLSERVICES/"
CODES = ("3009", "3010", "4000")


def _body(start: date, end: date) -> str:
    vals = "".join(f"<val{i}>{c}</val{i}>" for i, c in enumerate(CODES, start=5))
    return ('<?xml version="1.0" encoding="utf-8"?><message><proframeHeader>'
            "<pfmAppName>BIS-KOFIABOND</pfmAppName><pfmSvcName>BISLastAskPrcROPSrchSO</pfmSvcName>"
            "<pfmFnName>listTrm</pfmFnName></proframeHeader><systemHeader></systemHeader>"
            f"<BISComDspDatDTO><val1>DD</val1><val2>{start:%Y%m%d}</val2><val3>{end:%Y%m%d}</val3>"
            f"<val4>1530</val4>{vals}</BISComDspDatDTO></message>")


@lru_cache(maxsize=4)
def _table(start: date, end: date) -> pd.DataFrame:
    """세 코드를 한 번에 받는다. 기간이 길면 1년 단위로 나눠 요청한다."""
    frames = []
    s = start
    while s <= end:
        e = min(s + timedelta(days=365), end)
        r = request("POST", URL, data=_body(s, e).encode("utf-8"),
                    headers={"Content-Type": "text/xml; charset=utf-8"})
        root = ET.fromstring(r.content)
        rows = []
        for d in root.iter("BISComDspDatDTO"):
            vals = [(d.findtext(f"val{i}") or "").strip() for i in range(1, len(CODES) + 2)]
            if len(vals[0]) == 10 and vals[0][4] == "-":  # '최고'/'최저' 요약행 제외
                rows.append(vals)
        frames.append(pd.DataFrame(rows, columns=["date", *CODES]))
        s = e + timedelta(days=1)
    df = pd.concat(frames)
    return df.set_index(pd.to_datetime(df.pop("date")))


def fetch(params: dict, start: date, end: date) -> pd.Series:
    df = _table(start, end)
    if df.empty:
        raise RuntimeError("채권정보센터 응답에 데이터 없음")
    return clean(df[params["code"]].replace({"": None, "-": None}))
