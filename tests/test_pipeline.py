"""네트워크 없이 전체 흐름 확인: 일부 수집기 실패, 리포트 생성, 전부 실패 시 종료 코드."""
from datetime import timedelta

import numpy as np
import pandas as pd

from macro_monitor import main as m


def fake_ok(params, start, end):
    idx = pd.bdate_range(start, end)
    rng = np.random.default_rng(len(idx))
    v = 3 + rng.normal(0, 0.02, len(idx))
    v[-1] = 4.0
    return pd.Series(v, index=idx)


def fake_fail(params, start, end):
    raise RuntimeError("테스트 실패")


def test_partial_failure(tmp_path, monkeypatch):
    fetchers = {k: fake_ok for k in m.FETCHERS}
    fetchers["kofia"] = fake_fail
    monkeypatch.setattr(m, "FETCHERS", fetchers)
    rc = m.main(["--db", str(tmp_path / "t.db"), "--out", str(tmp_path / "site"), "--no-notify"])
    assert rc == 0
    html = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert "수집 오류" in html and "⚑" in html
    # 두 번째 실행은 증분 수집
    rc = m.main(["--db", str(tmp_path / "t.db"), "--out", str(tmp_path / "site"), "--no-notify"])
    assert rc == 0


def test_all_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "FETCHERS", {k: fake_fail for k in m.FETCHERS})
    rc = m.main(["--db", str(tmp_path / "t.db"), "--out", str(tmp_path / "site"), "--no-notify"])
    assert rc == 1
    assert (tmp_path / "site" / "index.html").exists()
