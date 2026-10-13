"""실행 진입점: python -m macro_monitor.main [--out site] [--no-notify] [--telegram-test]"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import detect, notify, report
from .sources import FETCHERS
from .storage import Store

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
log = logging.getLogger("macro_monitor")


def load_config(path: Path = ROOT / "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def thresholds(cfg: dict, ind: dict) -> dict:
    th = dict(cfg["defaults"])
    th.update(ind.get("thresholds") or {})
    return th


def collect(cfg: dict, store: Store, today) -> dict[str, dict]:
    """모든 지표 수집. 한 지표 실패가 다른 지표에 영향을 주지 않는다."""
    status: dict[str, dict] = {}
    for ind in cfg["indicators"]:
        iid = ind["id"]
        last = store.last_date(iid)
        start = (today - timedelta(days=cfg["backfill_days"]) if last is None
                 else min(last, today) - timedelta(days=cfg["refresh_days"]))
        t0 = time.time()
        try:
            s = FETCHERS[ind["source"]](ind.get("params", {}), start, today)
            n = store.upsert(iid, s)
            store.set_status(iid, True)
            status[iid] = {"ok": True, "rows": n, "error": ""}
            log.info("%-16s OK   %4d rows  %.1fs", iid, n, time.time() - t0)
        except Exception as e:  # noqa: BLE001 — 어떤 실패든 해당 지표만 오류 처리
            msg = f"{type(e).__name__}: {e}"[:300]
            store.set_status(iid, False, msg)
            status[iid] = {"ok": False, "rows": 0, "error": msg}
            log.warning("%-16s FAIL %s", iid, msg)
    return status


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "data" / "macro.db"))
    ap.add_argument("--out", default=str(ROOT / "site"))
    ap.add_argument("--no-notify", action="store_true", help="알림을 보내지 않는다 (테스트용)")
    ap.add_argument("--telegram-test", action="store_true", help="텔레그램 연결 테스트 메시지만 보내고 끝낸다")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.telegram_test:
        return 0 if notify.telegram_test() else 1

    cfg = load_config()
    now = datetime.now(KST)
    today = now.date()
    store = Store(args.db)

    fetch_status = collect(cfg, store, today)

    rows = []
    for ind in cfg["indicators"]:
        s = store.series(ind["id"])
        res = detect.evaluate(ind, s, thresholds(cfg, ind), today)
        rows.append({"ind": ind, "res": res, "fetch": fetch_status[ind["id"]], "series": s})

    report.write(rows, cfg, now, Path(args.out))
    log.info("리포트 작성: %s", Path(args.out) / "index.html")

    if not args.no_notify:
        notify.send(rows, cfg, now, store)

    store.close()

    n_ok = sum(1 for v in fetch_status.values() if v["ok"])
    log.info("수집 성공 %d / %d", n_ok, len(fetch_status))
    if n_ok == 0:
        log.error("모든 지표 수집 실패")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
