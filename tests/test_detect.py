from datetime import date

import numpy as np
import pandas as pd

from macro_monitor.detect import change, evaluate, summary_line
from macro_monitor.main import load_config, thresholds

CFG = load_config()
IND = {"id": "x", "name": "테스트 OAS", "change": "bp", "unit": "%p", "decimals": 2, "freq": "daily"}
TH = thresholds(CFG, IND)


def series(values, end="2026-10-12"):
    idx = pd.bdate_range(end=end, periods=len(values))
    return pd.Series(values, index=idx, dtype=float)


def calm(n=300, seed=0):
    rng = np.random.default_rng(seed)
    return list(3 + np.cumsum(rng.normal(0, 0.01, n)) * 0 + rng.normal(0, 0.02, n))


def test_change_units():
    assert abs(change(3.10, 3.00, "bp") - 10) < 1e-9
    assert abs(change(110, 100, "pct") - 10) < 1e-9
    assert change(5, 3, "abs") == 2


def test_calm_series_no_flags():
    r = evaluate(IND, series(calm()[:-1] + [3.0]), TH, date(2026, 10, 13))
    assert r.status == "ok"
    assert not r.flags


def test_spike_flags_z_high_and_change():
    vals = calm() + [3.6]
    r = evaluate(IND, series(vals), TH, date(2026, 10, 13))
    codes = {f.code for f in r.flags}
    assert {"z", "high", "chg1", "chg5"} <= codes
    line = summary_line(IND, r)
    assert line.startswith("테스트 OAS: 최근 1년 기준 z-score +")
    # 해석 문장이 섞이지 않았는지
    for word in ("신호", "국면", "리스크", "우려", "시사"):
        assert word not in line


def test_new_low():
    r = evaluate(IND, series(calm() + [2.0]), TH, date(2026, 10, 13))
    assert any(f.code == "low" for f in r.flags)


def test_insufficient_history():
    r = evaluate(IND, series(calm(30)), TH, date(2026, 10, 13))
    assert r.status == "insufficient"
    assert r.z is None and not r.flags
    assert r.chg1 is not None


def test_flat_repeat_is_not_new_high():
    vals = calm() + [3.5, 3.5]
    r = evaluate(IND, series(vals), TH, date(2026, 10, 13))
    assert not any(f.code == "high" for f in r.flags)


def test_stale_weekly():
    ind = {**IND, "freq": "weekly"}
    s = pd.Series(calm(60), index=pd.date_range(end="2026-09-23", periods=60, freq="W-WED"))
    r = evaluate(ind, s, TH, date(2026, 10, 13))
    assert r.stale and r.days_since == 20


def test_empty():
    assert evaluate(IND, pd.Series(dtype=float), TH, date(2026, 10, 13)).status == "no_data"
