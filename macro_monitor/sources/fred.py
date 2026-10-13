"""FRED 공식 API. FRED_API_KEY 환경변수(GitHub Secret)가 필요하다.

키 없이 받는 fredgraph.csv 경로는 GitHub Actions IP에서 응답하지 않아 쓰지 않는다.
"""
from __future__ import annotations

import os
from datetime import date

import pandas as pd

from ._http import clean, request


def fetch(params: dict, start: date, end: date) -> pd.Series:
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        raise RuntimeError("FRED_API_KEY 시크릿이 등록되지 않음")
    r = request("GET", "https://api.stlouisfed.org/fred/series/observations", params={
        "series_id": params["series"], "api_key": key, "file_type": "json",
        "observation_start": start.isoformat(), "observation_end": end.isoformat(),
    })
    obs = r.json()["observations"]
    s = clean(pd.Series({o["date"]: o["value"] for o in obs}, dtype=object))  # "." 은 결측
    return s * float(params.get("scale", 1))
