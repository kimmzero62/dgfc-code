"""DefiLlama 스테이블코인 총 시가총액 (USD 페그 합계, $bn)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from ._http import clean, request


def fetch(params: dict, start: date, end: date) -> pd.Series:
    data = request("GET", "https://stablecoins.llama.fi/stablecoincharts/all").json()
    s = pd.Series({pd.Timestamp(int(x["date"]), unit="s"): x["totalCirculatingUSD"].get("peggedUSD")
                   for x in data})
    s = clean(s) / 1e9
    return s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]
