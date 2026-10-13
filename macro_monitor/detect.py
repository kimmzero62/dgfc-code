"""이례적 움직임 감지. 해석은 하지 않고, 기준을 넘은 사실만 기록한다."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd


@dataclass
class Flag:
    code: str     # z | high | low | chg1 | chg5
    text: str     # 사실만 적은 짧은 문장


@dataclass
class Result:
    indicator_id: str
    status: str                      # ok | insufficient | no_data
    last_date: date | None = None
    value: float | None = None
    chg1: float | None = None        # 직전 관측 대비 (표시 단위)
    chg5: float | None = None        # 5영업일(7일 전 관측) 대비
    z: float | None = None           # 1년 창 z-score
    pct_rank: float | None = None    # 1년 창 백분위 (0~100)
    hi: float | None = None          # 1년 고점
    lo: float | None = None          # 1년 저점
    chg1_z: float | None = None      # 일간 변화의 과거 분포 대비 z
    chg5_z: float | None = None
    stale: bool = False
    days_since: int | None = None
    obs_in_window: int = 0
    flags: list[Flag] = field(default_factory=list)


def change(a, b, kind: str):
    """b → a 변화량. bp: %값 차이×100, pct: 변화율 %, abs: 차이."""
    if kind == "bp":
        return (a - b) * 100
    if kind == "pct":
        return (a / b - 1) * 100
    return a - b


def unit_of_change(kind: str, unit: str) -> str:
    return {"bp": "bp", "pct": "%"}.get(kind, unit)


def _value_asof(s: pd.Series, when: pd.Timestamp):
    """when 시점 또는 그 이전의 마지막 값."""
    sub = s[s.index <= when]
    return None if sub.empty else sub.iloc[-1]


def _changes_5d(s: pd.Series, kind: str) -> pd.Series:
    """각 관측일 t에 대해 x(t) - x(t-7일 시점의 값)."""
    left = pd.DataFrame({"t": s.index - pd.Timedelta(days=7), "x": s.values, "d": s.index})
    right = pd.DataFrame({"t": s.index, "base": s.values})
    m = pd.merge_asof(left.sort_values("t"), right, on="t", direction="backward")
    out = pd.Series(change(m["x"].values, m["base"].values, kind), index=m["d"].values)
    return out.dropna().sort_index()


def _zscore(x: float, sample: pd.Series):
    sample = sample.replace([np.inf, -np.inf], np.nan).dropna()
    if len(sample) < 10:
        return None
    sd = sample.std(ddof=1)
    if not np.isfinite(sd) or sd == 0:
        return None
    return float((x - sample.mean()) / sd)


def _fmt(x: float, decimals: int = 1, sign: bool = True) -> str:
    return f"{x:+.{decimals}f}" if sign else f"{x:.{decimals}f}"


def evaluate(indicator: dict, s: pd.Series, th: dict, as_of: date) -> Result:
    iid, kind, unit = indicator["id"], indicator.get("change", "abs"), indicator.get("unit", "")
    dec = int(indicator.get("decimals", 2))
    s = s.dropna().sort_index()
    if s.empty:
        return Result(iid, "no_data")

    last_d, last_v = s.index[-1], float(s.iloc[-1])
    r = Result(iid, "ok", last_d.date(), last_v)
    r.days_since = (pd.Timestamp(as_of) - last_d).days
    r.stale = r.days_since > th["stale_days"].get(indicator.get("freq", "daily"), 5)

    if len(s) >= 2:
        r.chg1 = float(change(last_v, s.iloc[-2], kind))
    base5 = _value_asof(s, last_d - pd.Timedelta(days=7))
    if base5 is not None:
        r.chg5 = float(change(last_v, base5, kind))

    win = s[s.index > last_d - pd.Timedelta(days=th["lookback_days"])]
    r.obs_in_window = len(win)
    span = (last_d - s.index[0]).days
    if span < th["min_history_days"] or len(win) < th["min_observations"]:
        r.status = "insufficient"
        return r

    r.z = _zscore(last_v, win)
    r.pct_rank = float((win <= last_v).mean() * 100)
    r.hi, r.lo = float(win.max()), float(win.min())
    prior = win.iloc[:-1]
    cu = unit_of_change(kind, unit)

    # 1) 수준 z-score
    if r.z is not None and abs(r.z) >= th["z_threshold"]:
        r.flags.append(Flag("z", f"최근 1년 기준 z-score {_fmt(r.z)}"))
    # 2) 1년 고점·저점 갱신 (직전까지의 1년 창 대비, 같은 값 반복은 갱신으로 보지 않음)
    if th.get("flag_new_high_low", True) and len(prior):
        if last_v > prior.max():
            r.flags.append(Flag("high", "최근 1년 고점 갱신"))
        elif last_v < prior.min():
            r.flags.append(Flag("low", "최근 1년 저점 갱신"))
    # 3) 단기 변화폭이 과거 1년 변화 분포 대비 극단
    hist = s[s.index > last_d - pd.Timedelta(days=th["lookback_days"] + 10)]
    d1 = pd.Series(change(hist.values[1:], hist.values[:-1], kind), index=hist.index[1:])
    d1 = d1[d1.index > last_d - pd.Timedelta(days=th["lookback_days"])]
    if r.chg1 is not None and len(d1) > 1:
        r.chg1_z = _zscore(r.chg1, d1.iloc[:-1])
        if r.chg1_z is not None and abs(r.chg1_z) >= th["change_z_threshold"]:
            r.flags.append(Flag("chg1", f"직전 관측 대비 {_fmt(r.chg1)}{cu} "
                                        f"(과거 1년 변화 분포 대비 z {_fmt(r.chg1_z)})"))
    d5 = _changes_5d(hist, kind)
    d5 = d5[d5.index > last_d - pd.Timedelta(days=th["lookback_days"])]
    if r.chg5 is not None and len(d5) > 1:
        r.chg5_z = _zscore(r.chg5, d5.iloc[:-1])
        if r.chg5_z is not None and abs(r.chg5_z) >= th["change_z_threshold"]:
            r.flags.append(Flag("chg5", f"5영업일 변화 {_fmt(r.chg5)}{cu} "
                                        f"(과거 1년 변화 분포 대비 z {_fmt(r.chg5_z)})"))
    return r


def summary_line(indicator: dict, r: Result) -> str:
    """알림용 한 줄. 예: 'CCC 이하 OAS: 최근 1년 기준 z-score +2.3, 5일간 +85bp (기준일 2026-10-12)'"""
    kind, unit = indicator.get("change", "abs"), indicator.get("unit", "")
    cu = unit_of_change(kind, unit)
    parts = [f.text for f in r.flags]
    if r.chg5 is not None and not any(f.code == "chg5" for f in r.flags):
        parts.append(f"5영업일 변화 {_fmt(r.chg5)}{cu}")
    return f"{indicator['name']}: " + ", ".join(parts) + f" (기준일 {r.last_date})"
