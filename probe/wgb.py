import re
import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}
BASE = "https://www.worldgovernmentbonds.com"
urls = [BASE + "/robots.txt", BASE + "/sovereign-cds/"]
urls += [f"{BASE}/cds-historical-data/{c}/5-years/" for c in
         ["france", "south-korea", "united-states", "germany", "italy", "spain", "united-kingdom", "japan", "china"]]
for i, url in enumerate(urls):
    try:
        r = requests.get(url, headers=UA, timeout=40)
    except Exception as e:
        print("###", url, "FAIL", e); continue
    t = r.text
    print("###", url, r.status_code, len(t), r.headers.get("server"), r.headers.get("content-type"), flush=True)
    if url.endswith("robots.txt"):
        print(t[:1500]); continue
    if i > 3:  # 나머지 국가는 접근 가능 여부만
        print("TITLE", re.findall(r"<title>(.*?)</title>", t, re.S)[:1]); continue
    print("TITLE", re.findall(r"<title>(.*?)</title>", t, re.S)[:1])
    print("SCRIPTS", re.findall(r'<script[^>]+src="([^"]+)"', t)[:40])
    for kw in ["admin-ajax", "wp-json", "ajax", "jsonData", "chartData", "nonce", "France"]:
        for m in list(re.finditer(kw, t))[:4]:
            s = t[max(0, m.start() - 200): m.end() + 400].replace("\n", " ")
            print(f"--[{kw}] {s}")
