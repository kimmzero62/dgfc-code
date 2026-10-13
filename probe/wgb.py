import re
import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}
for url in ["https://www.worldgovernmentbonds.com/robots.txt",
            "https://www.worldgovernmentbonds.com/cds-historical-data/south-korea/5-years/",
            "https://www.worldgovernmentbonds.com/sovereign-cds/"]:
    try:
        r = requests.get(url, headers=UA, timeout=40)
    except Exception as e:
        print("###", url, "FAIL", e); continue
    t = r.text
    print("###", url, r.status_code, len(t), r.headers.get("server"), r.headers.get("content-type"))
    if url.endswith("robots.txt"):
        print(t[:1500]); continue
    print("TITLE", re.findall(r"<title>(.*?)</title>", t, re.S)[:1])
    print("SCRIPTS", re.findall(r'<script[^>]+src="([^"]+)"', t)[:40])
    for kw in ["admin-ajax", "wp-json", "ajax", "jsonData", "chartData", "historical", "symbol", "nonce", "data-"]:
        for m in list(re.finditer(kw, t))[:4]:
            s = t[max(0, m.start() - 200): m.end() + 300].replace("\n", " ")
            print(f"--[{kw}] {s}")
    for m in list(re.finditer(r"South Korea", t))[:6]:
        print("--[KR]", t[m.start(): m.start() + 400].replace("\n", " "))
