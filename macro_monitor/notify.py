"""플래그 알림: GitHub 이슈(기본) + 텔레그램(시크릿이 있을 때).

같은 지표·같은 관측일·같은 플래그 조합은 한 번만 알린다 (하루 2회 실행, 주간 지표 중복 방지).
"""
from __future__ import annotations

import logging
import os

import requests

from .detect import summary_line

log = logging.getLogger("macro_monitor")


def pages_url() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in repo:
        return ""
    owner, name = repo.split("/", 1)
    return f"https://{owner.lower()}.github.io/{name}/"


def build_message(new_rows: list[dict], now) -> tuple[str, str]:
    title = f"매크로 플래그 {now:%Y-%m-%d %H:%M} KST · {len(new_rows)}개 지표"
    lines = [f"- {summary_line(r['ind'], r['res'])}" for r in new_rows]
    body = "\n".join(lines)
    url = pages_url()
    if url:
        body += f"\n\n대시보드: {url}"
    return title, body


def _github_issue(title: str, body: str, cfg: dict) -> bool:
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo):
        log.info("GITHUB_TOKEN 없음: 이슈 알림 생략")
        return False
    api = f"https://api.github.com/repos/{repo}"
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    label = cfg["alerts"].get("issue_label", "macro-flag")
    requests.post(f"{api}/labels", headers=h, json={"name": label, "color": "d03b3b"}, timeout=30)
    # 이전 알림 이슈는 닫아서 열린 이슈가 최신 것 하나만 남게 한다
    old = requests.get(f"{api}/issues", headers=h, params={"labels": label, "state": "open"}, timeout=30)
    for it in old.json() if old.ok else []:
        requests.patch(f"{api}/issues/{it['number']}", headers=h,
                       json={"state": "closed", "state_reason": "completed"}, timeout=30)
    mention = cfg["alerts"].get("mention")
    full = body + (f"\n\ncc @{mention}" if mention else "")
    r = requests.post(f"{api}/issues", headers=h, json={"title": title, "body": full, "labels": [label]},
                      timeout=30)
    if not r.ok:
        log.warning("이슈 생성 실패 %s %s", r.status_code, r.text[:200])
    return r.ok


def _telegram(title: str, body: str) -> bool:
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        return False
    r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      json={"chat_id": chat, "text": f"{title}\n\n{body}", "disable_web_page_preview": True},
                      timeout=30)
    if not r.ok:
        log.warning("텔레그램 전송 실패 %s %s", r.status_code, r.text[:200])
    return r.ok


def send(rows: list[dict], cfg: dict, now, store) -> None:
    new_rows = []
    for row in rows:
        res = row["res"]
        if not res.flags:
            continue
        codes = ",".join(sorted(f.code for f in res.flags))
        if not store.already_alerted(res.indicator_id, str(res.last_date), codes):
            new_rows.append(row)
    if not new_rows:
        log.info("새 플래그 없음: 알림 생략")
        return

    title, body = build_message(new_rows, now)
    log.info("알림 내용\n%s\n%s", title, body)
    sent = False
    if cfg["alerts"].get("github_issue", True):
        sent |= _github_issue(title, body, cfg)
    if cfg["alerts"].get("telegram", "auto"):
        sent |= _telegram(title, body)
    if sent:
        for row in new_rows:
            res = row["res"]
            store.mark_alerted(res.indicator_id, str(res.last_date),
                               ",".join(sorted(f.code for f in res.flags)))
