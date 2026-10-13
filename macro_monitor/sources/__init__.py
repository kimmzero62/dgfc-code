"""데이터 수집기 모음.

모든 수집기는 fetch(params: dict, start: date, end: date) -> pd.Series 형태다.
반환 시리즈는 DatetimeIndex(날짜, 시간 없음), float 값, 오름차순이어야 한다.
"""
from __future__ import annotations

from . import acm, defillama, fred, kofia, manual, mof_jgb, tga, yfin

FETCHERS = {
    "fred": fred.fetch,
    "acm": acm.fetch,
    "yfinance": yfin.fetch,
    "bkln_discount": yfin.fetch_nav_discount,
    "tga": tga.fetch,
    "mof_jgb": mof_jgb.fetch,
    "manual": manual.fetch,
    "defillama": defillama.fetch,
    "kofia": kofia.fetch,
}
