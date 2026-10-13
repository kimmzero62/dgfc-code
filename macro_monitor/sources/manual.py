"""수동 입력 지표 (manual/manual_inputs.csv).

CSV 열: date,key,value  — GitHub 웹에서 파일을 직접 편집해 한 줄씩 추가하면 된다.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from ._http import clean

PATH = Path(__file__).resolve().parents[2] / "manual" / "manual_inputs.csv"


def fetch(params: dict, start: date, end: date) -> pd.Series:
    if not PATH.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(PATH, comment="#", skipinitialspace=True)
    df = df[df["key"].astype(str).str.strip() == params["key"]]
    return clean(pd.Series(df["value"].values, index=df["date"].astype(str).str.strip()))
