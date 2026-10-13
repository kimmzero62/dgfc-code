"""미 재무부 Daily Treasury Statement — TGA 마감 잔고 ($bn)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from ._http import clean, request

URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance"


def fetch(params: dict, start: date, end: date) -> pd.Series:
    r = request("GET", URL, params={
        "filter": f"record_date:gte:{start.isoformat()},record_date:lte:{end.isoformat()},"
                  "account_type:eq:Treasury General Account (TGA) Closing Balance",
        "fields": "record_date,open_today_bal",
        "page[size]": 10000, "sort": "record_date",
    })
    rows = r.json()["data"]
    if not rows:
        raise RuntimeError("DTS 응답에 TGA Closing Balance 없음")
    # 2021-10 이후 서식에서 마감 잔고는 open_today_bal 열에 들어 있다 (단위: 백만 달러)
    s = clean(pd.Series({x["record_date"]: x["open_today_bal"] for x in rows}, dtype=object))
    return s / 1000
