"""데이터 소스 검증 스크립트.

각 후보 소스에서 실제로 최신 데이터가 받아지는지 확인하고 결과를 표로 출력한다.
GitHub Actions(해외 IP)에서 실행하는 것을 전제로 한다. API 키가 없으면 키 없이 가능한
경로(FRED fredgraph.csv, ECOS sample 키)로 시도한다.
"""
from __future__ import annotations

import io
import json
import os
import signal
import sys
import time
import traceback
from datetime import date, datetime, timedelta

import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
TIMEOUT = 30
FRED_KEY = os.environ.get("FRED_API_KEY", "")
ECOS_KEY = os.environ.get("ECOS_API_KEY", "") or "sample"

results: list[dict] = []


class CheckTimeout(Exception):
    pass


def _alarm(signum, frame):
    raise CheckTimeout("항목당 60초 초과")


def record(indicator: str, source: str, fn):
    t0 = time.time()
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(60)
    try:
        info = fn()
        status = "OK" if info.get("rows", 0) > 0 else "EMPTY"
        results.append({"indicator": indicator, "source": source, "status": status,
                        "latest": str(info.get("latest", "")), "latest_value": info.get("value", ""),
                        "rows": info.get("rows", 0), "note": info.get("note", ""),
                        "secs": round(time.time() - t0, 1)})
    except Exception as e:  # noqa: BLE001
        results.append({"indicator": indicator, "source": source, "status": "FAIL",
                        "latest": "", "latest_value": "", "rows": 0,
                        "note": f"{type(e).__name__}: {str(e)[:180]}", "secs": round(time.time() - t0, 1)})
        traceback.print_exc()
    finally:
        signal.alarm(0)
    print("RESULT " + json.dumps(results[-1], ensure_ascii=False, default=str), flush=True)


def summarize(s: pd.Series, note: str = "") -> dict:
    s = s.dropna()
    if s.empty:
        return {"rows": 0, "note": note or "no data"}
    return {"rows": len(s), "latest": pd.Timestamp(s.index[-1]).date(), "value": round(float(s.iloc[-1]), 4), "note": note}


# ---------- FRED ----------
def fred_csv(series_id: str) -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={(date.today() - timedelta(days=400)).isoformat()}"
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    return pd.to_numeric(df.set_index("date")["value"], errors="coerce")


def fred_api(series_id: str) -> pd.Series:
    r = requests.get("https://api.stlouisfed.org/fred/series/observations",
                     params={"series_id": series_id, "api_key": FRED_KEY, "file_type": "json",
                             "observation_start": (date.today() - timedelta(days=400)).isoformat()},
                     timeout=TIMEOUT)
    r.raise_for_status()
    obs = r.json()["observations"]
    s = pd.Series({pd.Timestamp(o["date"]): o["value"] for o in obs})
    return pd.to_numeric(s, errors="coerce")


def check_fred(series_id: str):
    def _f():
        if FRED_KEY:
            return summarize(fred_api(series_id), "FRED API")
        return summarize(fred_csv(series_id), "fredgraph.csv(키 없음)")
    return _f


# ---------- yfinance ----------
def check_yf(ticker: str):
    def _f():
        import yfinance as yf
        df = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=False, threads=False)
        if df is None or df.empty:
            return {"rows": 0, "note": "yfinance empty"}
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        return summarize(close, f"yfinance {yf.__version__}")
    return _f


def check_stooq(ticker: str):
    def _f():
        r = requests.get(f"https://stooq.com/q/d/l/?s={ticker}&i=d", headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        if not r.text.startswith("Date"):
            return {"rows": 0, "note": "non-CSV: " + r.text[:120].replace("\n", " ")}
        df = pd.read_csv(io.StringIO(r.text), parse_dates=["Date"]).set_index("Date")
        return summarize(df["Close"], "stooq")
    return _f


# ---------- NY Fed ACM ----------
def check_acm():
    urls = [
        "https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xls",
        "https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xlsx",
    ]
    last_err = ""
    for url in urls:
        r = requests.get(url, headers=UA, timeout=60)
        if r.status_code != 200:
            last_err = f"{url.rsplit('/', 1)[-1]} HTTP {r.status_code}"
            continue
        xls = pd.ExcelFile(io.BytesIO(r.content))
        sheet = next((s for s in xls.sheet_names if "daily" in s.lower()), xls.sheet_names[0])
        df = xls.parse(sheet)
        date_col = df.columns[0]
        tp_col = next((c for c in df.columns if str(c).upper() in ("ACMTP10", "ACMTP10 ")), None)
        if tp_col is None:
            return {"rows": 0, "note": f"sheet={sheet} cols={list(df.columns)[:8]}"}
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True)
        s = pd.to_numeric(df.set_index(date_col)[tp_col], errors="coerce")
        return summarize(s, f"{url.rsplit('/', 1)[-1]} sheet={sheet}")
    return {"rows": 0, "note": last_err}


# ---------- BKLN NAV ----------
def check_bkln_nav():
    import yfinance as yf
    notes = []
    try:
        info = yf.Ticker("BKLN").info
        nav = info.get("navPrice")
        notes.append(f"yf.info navPrice={nav}")
        if nav:
            return {"rows": 1, "latest": date.today(), "value": nav, "note": "; ".join(notes) + " (이력 없음, 누적 필요)"}
    except Exception as e:  # noqa: BLE001
        notes.append(f"yf.info err {type(e).__name__}")
    for url in [
        "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/BKLN/prices?idType=ticker&productType=ETF",
        "https://www.invesco.com/us/financial-products/etfs/product-detail?audienceType=Investor&ticker=BKLN",
    ]:
        try:
            r = requests.get(url, headers=UA, timeout=TIMEOUT)
            notes.append(f"{url.split('/')[2]} HTTP {r.status_code} len={len(r.text)} nav_in_body={'nav' in r.text.lower()}")
            if r.status_code == 200 and url.startswith("https://dng-api"):
                notes.append(r.text[:200].replace("\n", " "))
        except Exception as e:  # noqa: BLE001
            notes.append(f"{url.split('/')[2]} {type(e).__name__}")
    return {"rows": 0, "note": "; ".join(notes)}


# ---------- TGA (Daily Treasury Statement) ----------
def check_tga():
    r = requests.get(
        "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance",
        params={"filter": f"record_date:gte:{(date.today() - timedelta(days=400)).isoformat()}",
                "page[size]": 10000, "sort": "record_date"},
        timeout=TIMEOUT)
    r.raise_for_status()
    df = pd.DataFrame(r.json()["data"])
    types = sorted(df["account_type"].unique().tolist())
    sel = df[df["account_type"].str.contains("Closing Balance", case=False)]
    val_col = "open_today_bal" if "open_today_bal" in sel.columns else sel.columns[-1]
    s = pd.to_numeric(sel.set_index(pd.to_datetime(sel["record_date"]))[val_col], errors="coerce")
    return summarize(s, f"DTS account_types={types[:4]} col={val_col}")


# ---------- Japan 30Y (MOF) ----------
def _mof_parse(text: str) -> pd.Series:
    lines = text.splitlines()
    hdr = next(i for i, l in enumerate(lines) if l.startswith("Date") or l.startswith("基準日"))
    df = pd.read_csv(io.StringIO("\n".join(lines[hdr:])))
    col30 = next(c for c in df.columns if str(c).strip() in ("30Y", "30年"))
    d = df.iloc[:, 0].astype(str)
    idx = pd.to_datetime(d, errors="coerce", format="mixed")
    return pd.to_numeric(pd.Series(df[col30].values, index=idx), errors="coerce").dropna()


def check_jgb30():
    out = []
    for url in ["https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv",
                "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv"]:
        r = requests.get(url, headers=UA, timeout=60)
        r.raise_for_status()
        out.append(_mof_parse(r.content.decode("utf-8", errors="replace")))
    s = pd.concat(out).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    s = s[s.index >= pd.Timestamp(date.today() - timedelta(days=400))]
    return summarize(s, "MOF jgbcme.csv + jgbcme_all.csv")


# ---------- DefiLlama ----------
def check_defillama():
    r = requests.get("https://stablecoins.llama.fi/stablecoincharts/all", headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    s = pd.Series({pd.Timestamp(int(x["date"]), unit="s"): x["totalCirculatingUSD"].get("peggedUSD") for x in data})
    return summarize(s, "stablecoincharts/all peggedUSD")


# ---------- ECOS ----------
def ecos_items(stat_code: str) -> list[dict]:
    url = f"https://ecos.bok.or.kr/api/StatisticItemList/{ECOS_KEY}/json/kr/1/100/{stat_code}"
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    j = r.json()
    if "StatisticItemList" not in j:
        raise RuntimeError(str(j)[:200])
    return j["StatisticItemList"]["row"]


def check_ecos(name_keyword: str, fallback_code: str):
    def _f():
        stat = "817Y002"  # 시장금리(일별)
        code, note = fallback_code, f"key={'sample' if ECOS_KEY == 'sample' else 'secret'}"
        try:
            items = ecos_items(stat)
            match = [i for i in items if name_keyword in i["ITEM_NAME"]]
            if match:
                code = match[0]["ITEM_CODE"]
                note += f" item={match[0]['ITEM_NAME']}({code})"
            else:
                note += f" item_list={len(items)}개 중 '{name_keyword}' 없음, fallback {code}"
        except Exception as e:  # noqa: BLE001
            note += f" itemlist err {str(e)[:80]}"
        end = date.today().strftime("%Y%m%d")
        start = (date.today() - timedelta(days=20 if ECOS_KEY == "sample" else 400)).strftime("%Y%m%d")
        url = f"https://ecos.bok.or.kr/api/StatisticSearch/{ECOS_KEY}/json/kr/1/1000/{stat}/D/{start}/{end}/{code}"
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        j = r.json()
        if "StatisticSearch" not in j:
            return {"rows": 0, "note": note + " " + str(j)[:150]}
        rows = j["StatisticSearch"]["row"]
        s = pd.Series({pd.Timestamp(x["TIME"]): x["DATA_VALUE"] for x in rows})
        return summarize(pd.to_numeric(s, errors="coerce").sort_index(), note)
    return _f


# ---------- 외국인 순매수 ----------
def check_pykrx():
    from pykrx import stock
    end = date.today().strftime("%Y%m%d")
    start = (date.today() - timedelta(days=20)).strftime("%Y%m%d")
    df = stock.get_market_trading_value_by_date(start, end, "KOSPI")
    if df is None or df.empty:
        return {"rows": 0, "note": "pykrx empty"}
    col = next((c for c in df.columns if "외국인" in c), df.columns[0])
    return summarize(df[col] / 1e8, f"pykrx col={col} (억원)")


def check_naver_foreign():
    url = "https://finance.naver.com/sise/investorDealTrendDay.naver"
    r = requests.get(url, params={"bizdate": date.today().strftime("%Y%m%d"), "sosok": "01", "page": 1},
                     headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    tables = pd.read_html(io.StringIO(r.content.decode("euc-kr", errors="replace")))
    t = tables[0].dropna(how="all")
    t = t[t.iloc[:, 0].astype(str).str.match(r"\d{2}\.\d{2}\.\d{2}")]
    idx = pd.to_datetime(t.iloc[:, 0], format="%y.%m.%d")
    s = pd.to_numeric(pd.Series(t.iloc[:, 2].values, index=idx), errors="coerce").sort_index()
    return summarize(s, "naver 투자자별 매매동향(코스피, 외국인 열, 억원)")


def check_telegram():
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not tok:
        r = requests.get("https://api.telegram.org/", timeout=TIMEOUT)
        return {"rows": 1, "latest": date.today(), "note": f"토큰 없음, api.telegram.org HTTP {r.status_code}"}
    r = requests.get(f"https://api.telegram.org/bot{tok}/getMe", timeout=TIMEOUT)
    return {"rows": int(r.ok), "latest": date.today(), "note": f"getMe {r.status_code}"}


def main():
    for sid, name in [("DGS30", "미국채 30년"), ("T10Y2Y", "10Y-2Y 스프레드"), ("DFII10", "10Y 실질금리"),
                      ("BAMLC0A0CM", "IG OAS"), ("BAMLH0A0HYM2", "HY OAS"), ("BAMLH0A3HYC", "CCC 이하 OAS"),
                      ("WRESBAL", "지급준비금"), ("WTREGEN", "TGA(FRED 주간)"), ("THREEFYTP10", "텀프리미엄 대체(Kim-Wright)"),
                      ("DEXJPUS", "엔/달러(FRED 대체)")]:
        record(name, f"FRED {sid}", check_fred(sid))
    record("10Y 텀프리미엄(ACM)", "NY Fed ACM xls", check_acm)
    for t, name in [("^MOVE", "MOVE"), ("BKLN", "BKLN 가격"), ("JPY=X", "엔/달러"), ("ORCL", "ORCL"),
                    ("CRWV", "CRWV"), ("OWL", "OWL"), ("BX", "BX"), ("APO", "APO"), ("ARES", "ARES")]:
        record(name, f"yfinance {t}", check_yf(t))
    record("BKLN NAV", "yfinance info / Invesco", check_bkln_nav)
    record("ORCL(대체)", "stooq orcl.us", check_stooq("orcl.us"))
    record("TGA(일간)", "Treasury DTS API", check_tga)
    record("일본 30년물", "MOF CSV", check_jgb30)
    record("스테이블코인 시총", "DefiLlama", check_defillama)
    record("회사채 AA- 3년", "ECOS 817Y002", check_ecos("AA-", "010320000"))
    record("회사채 BBB- 3년", "ECOS 817Y002", check_ecos("BBB-", "010330000"))
    record("CD 91일", "ECOS 817Y002", check_ecos("CD", "010502000"))
    record("외국인 순매수", "pykrx", check_pykrx)
    record("외국인 순매수(대체)", "Naver Finance", check_naver_foreign)
    record("텔레그램", "api.telegram.org", check_telegram)

    df = pd.DataFrame(results)
    md = df.to_markdown(index=False)
    print("\n" + md)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"## 데이터 소스 검증 ({datetime.utcnow():%Y-%m-%d %H:%M} UTC)\n\n{md}\n")
    print("JSON_RESULTS=" + json.dumps(results, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
