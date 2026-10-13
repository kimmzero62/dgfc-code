from datetime import date

from macro_monitor.sources import wgb_cds


class Resp:
    def __init__(self, text="", js=None):
        self.text, self._js = text, js

    def json(self):
        return self._js


def test_wgb_cds_parses_and_drops_weekends(monkeypatch):
    page = 'x <script> var jsGlobalVars = {"FUNCTION":"CDS","COUNTRY1":{"SYMBOL":"3"}}; </script>'
    quote = {str(i): {"CLOSE_VAL": v, "DATA_VAL": d} for i, (d, v) in enumerate(
        [("2026-10-09", 70.1), ("2026-10-10", 70.1), ("2026-10-11", 70.1), ("2026-10-12", 72.4)])}
    calls = []

    def fake(method, url, **kw):
        calls.append((method, kw.get("json")))
        return Resp(page) if method == "GET" else Resp(js={"success": True, "result": {"quote": quote}})

    monkeypatch.setattr(wgb_cds, "request", fake)
    monkeypatch.setattr(wgb_cds.time, "sleep", lambda s: None)
    s = wgb_cds.fetch({"country": "france"}, date(2026, 10, 1), date(2026, 10, 13))
    assert calls[1] == ("POST", {"GLOBALVAR": {"FUNCTION": "CDS", "COUNTRY1": {"SYMBOL": "3"}}})
    assert list(s.index.strftime("%Y-%m-%d")) == ["2026-10-09", "2026-10-12"]  # 토·일 제외
    assert s.iloc[-1] == 72.4


def test_telegram_strips_whitespace(monkeypatch):
    from macro_monitor import notify

    sent = {}

    class R:
        ok, status_code, text = True, 200, "{}"

    def fake_post(url, json=None, timeout=None):
        sent["url"], sent["chat"] = url, json["chat_id"]
        return R()

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc\n")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", " 42 \n")
    monkeypatch.setattr(notify.requests, "post", fake_post)
    assert notify.telegram_test()
    assert sent["url"] == "https://api.telegram.org/bot123:abc/sendMessage"
    assert sent["chat"] == "42"
