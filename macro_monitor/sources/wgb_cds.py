"""worldgovernmentbonds.com 국가 CDS (5년, bp).

국가 페이지에 들어 있는 jsGlobalVars 를 읽어 사이트의 historical API 에 그대로 POST 한다.
사이트는 주말에도 직전 값을 채워 넣으므로 평일 값만 쓴다.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date

import pandas as pd

from ._http import clean, request

SITE = "https://www.worldgovernmentbonds.com"
ENDPOINT = SITE + "/wp-json/common/v1/historical"


def fetch(params: dict, start: date, end: date) -> pd.Series:
    page = f"{SITE}/cds-historical-data/{params['country']}/{params.get('tenor', '5-years')}/"
    html = request("GET", page).text
    m = re.search(r"var jsGlobalVars = (\{.*?\});", html, re.S)
    if not m:
        raise RuntimeError("페이지에서 jsGlobalVars 를 찾지 못함 (사이트 구조 변경 가능성)")
    time.sleep(1)  # 사이트 부담을 줄이기 위한 간격
    r = request("POST", ENDPOINT, json={"GLOBALVAR": json.loads(m.group(1))},
                headers={"Referer": page, "Origin": SITE})
    j = r.json()
    quote = (j.get("result") or {}).get("quote") if j.get("success") else None
    if not quote:
        raise RuntimeError("CDS API 응답에 데이터 없음")
    s = clean(pd.Series({q["DATA_VAL"]: q["CLOSE_VAL"] for q in quote.values()}, dtype=object))
    s = s[s.index.dayofweek < 5]
    return s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]
