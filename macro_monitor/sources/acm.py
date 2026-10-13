"""뉴욕연은 ACM 텀프리미엄 (엑셀 파일, 일간, 수일 지연 발표)."""
from __future__ import annotations

import io
from datetime import date

import pandas as pd

from ._http import clean, request

URL = "https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xls"


def fetch(params: dict, start: date, end: date) -> pd.Series:
    r = request("GET", URL)
    xls = pd.ExcelFile(io.BytesIO(r.content))
    sheet = next((s for s in xls.sheet_names if "daily" in s.lower()), xls.sheet_names[0])
    df = xls.parse(sheet)
    col = next(c for c in df.columns if str(c).strip().upper() == params["column"].upper())
    dates = pd.to_datetime(df.iloc[:, 0], errors="coerce", dayfirst=True)
    s = clean(pd.Series(df[col].values, index=dates))
    return s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]
