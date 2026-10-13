"""SQLite 저장소. data/macro.db 를 저장소에 커밋해 다음 실행이 이어받는다."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    indicator_id TEXT NOT NULL,
    date         TEXT NOT NULL,       -- YYYY-MM-DD
    value        REAL NOT NULL,
    PRIMARY KEY (indicator_id, date)
);
CREATE TABLE IF NOT EXISTS fetch_status (
    indicator_id TEXT PRIMARY KEY,
    last_attempt TEXT,                -- UTC ISO
    ok           INTEGER,
    error        TEXT,
    last_success TEXT
);
CREATE TABLE IF NOT EXISTS alerted (
    indicator_id TEXT NOT NULL,
    obs_date     TEXT NOT NULL,       -- 알림을 보낸 관측일
    flags        TEXT NOT NULL,
    alerted_at   TEXT NOT NULL,
    PRIMARY KEY (indicator_id, obs_date)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.commit()
        # 커밋되는 파일 하나로 끝나도록 WAL 등 부속 파일을 남기지 않는다
        with closing(self.conn.cursor()) as c:
            c.execute("VACUUM")
        self.conn.close()

    # ---- 관측치 ----
    def upsert(self, indicator_id: str, s: pd.Series) -> int:
        rows = [(indicator_id, d.strftime("%Y-%m-%d"), float(v)) for d, v in s.items()]
        self.conn.executemany(
            "INSERT INTO observations VALUES (?,?,?) "
            "ON CONFLICT(indicator_id, date) DO UPDATE SET value=excluded.value", rows)
        return len(rows)

    def series(self, indicator_id: str) -> pd.Series:
        rows = self.conn.execute(
            "SELECT date, value FROM observations WHERE indicator_id=? ORDER BY date",
            (indicator_id,)).fetchall()
        if not rows:
            return pd.Series(dtype=float)
        d, v = zip(*rows)
        return pd.Series(v, index=pd.DatetimeIndex(pd.to_datetime(list(d))), dtype=float)

    def last_date(self, indicator_id: str):
        row = self.conn.execute(
            "SELECT MAX(date) FROM observations WHERE indicator_id=?", (indicator_id,)).fetchone()
        return pd.Timestamp(row[0]).date() if row and row[0] else None

    # ---- 수집 상태 ----
    def set_status(self, indicator_id: str, ok: bool, error: str = "") -> None:
        now = _now()
        self.conn.execute(
            "INSERT INTO fetch_status VALUES (?,?,?,?,?) ON CONFLICT(indicator_id) DO UPDATE SET "
            "last_attempt=excluded.last_attempt, ok=excluded.ok, error=excluded.error, "
            "last_success=COALESCE(excluded.last_success, fetch_status.last_success)",
            (indicator_id, now, int(ok), error, now if ok else None))

    # ---- 알림 중복 방지 ----
    def already_alerted(self, indicator_id: str, obs_date: str, flags: str) -> bool:
        row = self.conn.execute(
            "SELECT flags FROM alerted WHERE indicator_id=? AND obs_date=?",
            (indicator_id, obs_date)).fetchone()
        return bool(row) and row[0] == flags

    def mark_alerted(self, indicator_id: str, obs_date: str, flags: str) -> None:
        self.conn.execute(
            "INSERT INTO alerted VALUES (?,?,?,?) ON CONFLICT(indicator_id, obs_date) DO UPDATE SET "
            "flags=excluded.flags, alerted_at=excluded.alerted_at",
            (indicator_id, obs_date, flags, _now()))
