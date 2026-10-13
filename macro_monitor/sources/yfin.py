"""yfinance 가격, BKLN NAV 대비 괴리율."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from ._http import clean


def _close(ticker: str, start: date, end: date) -> pd.Series:
    import yfinance as yf

    df = yf.download(ticker, start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                     interval="1d", progress=False, auto_adjust=False, threads=False)
    if df is None or df.empty:
        raise RuntimeError(f"yfinance {ticker}: 빈 응답")
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return clean(close)


def fetch(params: dict, start: date, end: date) -> pd.Series:
    return _close(params["ticker"], start, end)


def fetch_nav_discount(params: dict, start: date, end: date) -> pd.Series:
    """(종가 / NAV - 1) × 100.

    NAV는 무료 소스에서 이력을 받을 수 없어 yfinance의 현재 navPrice만 쓴다.
    따라서 매 실행마다 '가장 최근 거래일' 한 점을 만들고, 이력은 DB에 누적된다.
    """
    import yfinance as yf

    nav = yf.Ticker(params["ticker"]).info.get("navPrice")
    if not nav:
        raise RuntimeError("navPrice 없음")
    px = _close(params["ticker"], end - timedelta(days=10), end)
    last_day = px.index[-1]
    return pd.Series([(px.iloc[-1] / float(nav) - 1) * 100], index=pd.DatetimeIndex([last_day]))
