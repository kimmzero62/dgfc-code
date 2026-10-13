from __future__ import annotations

import time

import pandas as pd
import requests

UA = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124 Safari/537.36"
}
TIMEOUT = (15, 60)


def request(method: str, url: str, retries: int = 2, **kw) -> requests.Response:
    """간단한 재시도 포함 요청. 마지막 시도의 예외를 그대로 올린다."""
    kw.setdefault("timeout", TIMEOUT)
    kw["headers"] = {**UA, **kw.get("headers", {})}
    for attempt in range(retries + 1):
        try:
            r = requests.request(method, url, **kw)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == retries:
                raise
            time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


def clean(s: pd.Series) -> pd.Series:
    """날짜 정규화, 숫자 변환, 결측·중복 제거, 정렬."""
    s = pd.to_numeric(s, errors="coerce")
    s.index = pd.DatetimeIndex(pd.to_datetime(s.index)).normalize()
    s = s.dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.astype(float)
