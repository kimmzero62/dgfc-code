"""일본 재무성 국채 금리 CSV (당월분 + 전체 이력)."""
from __future__ import annotations

import io
from datetime import date

import pandas as pd

from ._http import clean, request

BASE = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/"


def _parse(text: str, tenor: str) -> pd.Series:
    lines = text.splitlines()
    hdr = next(i for i, l in enumerate(lines) if l.startswith("Date"))
    df = pd.read_csv(io.StringIO("\n".join(lines[hdr:])))
    col = next(c for c in df.columns if str(c).strip() == tenor)
    idx = pd.to_datetime(df.iloc[:, 0].astype(str), errors="coerce", format="mixed")
    return pd.Series(df[col].values, index=idx)


def fetch(params: dict, start: date, end: date) -> pd.Series:
    parts = []
    files = ["jgbcme.csv"]
    if (end - start).days > 40:  # 백필이나 월초에는 전체 이력 파일도 받는다
        files.insert(0, "historical/jgbcme_all.csv")
    for f in files:
        r = request("GET", BASE + f)
        parts.append(_parse(r.content.decode("utf-8", errors="replace"), params["tenor"]))
    s = clean(pd.concat(parts).dropna())
    return s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]
