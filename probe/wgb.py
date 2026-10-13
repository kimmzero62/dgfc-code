import json
import re
import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}
PAGE = "https://www.worldgovernmentbonds.com/cds-historical-data/france/5-years/"
EP = "https://www.worldgovernmentbonds.com/wp-json/common/v1/historical"
t = requests.get(PAGE, headers=UA, timeout=40).text
gv = json.loads(re.search(r"var jsGlobalVars = (\{.*?\});", t, re.S).group(1))
# 테마 JS 파일 찾기
js = sorted(set(re.findall(r'["\'](https://www\.worldgovernmentbonds\.com/wp-content/[^"\']+?\.js[^"\']*)["\']', t)))
print("JS FILES", js)
for u in js:
    try:
        s = requests.get(u, headers=UA, timeout=30).text
    except Exception as e:
        print("JS FAIL", u, e); continue
    for kw in ["ENDPOINT", "historical", "fetch(", "ajax("]:
        for m in list(re.finditer(re.escape(kw), s))[:3]:
            print(f"--{u.rsplit('/',1)[-1]} [{kw}]", s[max(0, m.start()-300): m.end()+500].replace("\n", " "))
h = {**UA, "Referer": PAGE, "Origin": "https://www.worldgovernmentbonds.com",
     "Content-Type": "application/json", "Accept": "application/json, text/javascript, */*"}
tries = [
    ("POST json GLOBALVAR", lambda: requests.post(EP, headers=h, json={"GLOBALVAR": gv}, timeout=40)),
    ("POST json raw", lambda: requests.post(EP, headers=h, json=gv, timeout=40)),
    ("POST form GLOBALVAR", lambda: requests.post(EP, headers={k: v for k, v in h.items() if k != "Content-Type"},
                                                  data={"GLOBALVAR": json.dumps(gv)}, timeout=40)),
    ("GET", lambda: requests.get(EP, headers=h, timeout=40)),
]
for name, fn in tries:
    try:
        r = fn()
        print(f"### {name} HTTP {r.status_code} ct={r.headers.get('content-type')} len={len(r.text)}")
        print(r.text[:1500])
    except Exception as e:
        print("###", name, "FAIL", e)
