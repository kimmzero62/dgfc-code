import sqlite3
from datetime import datetime

from macro_monitor import slot
from macro_monitor.slot import KST, should_skip, slot_of


def kst(*a):
    return datetime(*a, tzinfo=KST)


def test_slot_names():
    assert slot_of(kst(2026, 10, 14, 7, 7)) == "2026-10-14-morning"
    assert slot_of(kst(2026, 10, 14, 11, 59)) == "2026-10-14-morning"
    assert slot_of(kst(2026, 10, 14, 16, 47)) == "2026-10-14-evening"
    # 저녁 스케줄이 자정을 넘겨 늦게 돈 경우는 전날 저녁 슬롯
    assert slot_of(kst(2026, 10, 15, 0, 32)) == "2026-10-14-evening"


def test_backup_schedule_skips_after_done(tmp_path):
    db = tmp_path / "m.db"
    now = kst(2026, 10, 14, 7, 37)
    assert should_skip("schedule", now, db) == (False, "2026-10-14-morning")  # DB 없음
    with sqlite3.connect(db) as conn:
        assert should_skip("schedule", now, db)[0] is False                   # 테이블 없음
        slot.mark_done(conn, "2026-10-14-morning")
    assert should_skip("schedule", now, db)[0] is True                        # 예비 실행은 건너뜀
    assert should_skip("workflow_dispatch", now, db)[0] is False              # 수동 실행은 항상
    assert should_skip("schedule", kst(2026, 10, 14, 16, 47), db)[0] is False # 저녁 슬롯은 별개
