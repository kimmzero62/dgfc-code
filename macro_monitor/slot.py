"""실행 슬롯 관리: 같은 시간대(아침/저녁)에 예비 스케줄이 여러 번 돌아도 한 번만 실행한다.

GitHub 스케줄은 시각을 보장하지 않아 예비 cron 을 여러 개 걸어 두고,
이미 성공한 슬롯이면 뒤따르는 스케줄 실행은 바로 끝낸다. 표준 라이브러리만 쓴다.

  python -m macro_monitor.slot check --event schedule   # GITHUB_OUTPUT 에 skip=true/false
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
DB = Path(__file__).resolve().parents[1] / "data" / "macro.db"
SCHEMA = "CREATE TABLE IF NOT EXISTS run_slots (slot TEXT PRIMARY KEY, completed_at TEXT NOT NULL)"


def slot_of(now: datetime) -> str:
    """KST 기준 슬롯 이름.

    05:00~11:59 → 그날 morning, 12:00~23:59 → 그날 evening,
    00:00~04:59 → 전날 evening (저녁 스케줄이 자정을 넘겨 늦게 도는 경우)
    """
    t = now.astimezone(KST)
    if t.hour < 5:
        return f"{(t - timedelta(days=1)):%Y-%m-%d}-evening"
    return f"{t:%Y-%m-%d}-{'morning' if t.hour < 12 else 'evening'}"


def is_done(conn: sqlite3.Connection, slot: str) -> bool:
    conn.execute(SCHEMA)
    return conn.execute("SELECT 1 FROM run_slots WHERE slot=?", (slot,)).fetchone() is not None


def mark_done(conn: sqlite3.Connection, slot: str) -> None:
    conn.execute(SCHEMA)
    conn.execute("INSERT OR REPLACE INTO run_slots VALUES (?, ?)",
                 (slot, datetime.now(timezone.utc).isoformat(timespec="seconds")))


def should_skip(event: str, now: datetime, db: Path = DB) -> tuple[bool, str]:
    slot = slot_of(now)
    if event != "schedule":  # 수동 실행은 항상 돈다
        return False, slot
    if not db.exists():
        return False, slot
    with sqlite3.connect(db) as conn:
        return is_done(conn, slot), slot


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check"])
    ap.add_argument("--event", default="workflow_dispatch")
    args = ap.parse_args(argv)
    skip, slot = should_skip(args.event, datetime.now(KST))
    print(f"slot={slot} event={args.event} skip={str(skip).lower()}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"skip={str(skip).lower()}\nslot={slot}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
