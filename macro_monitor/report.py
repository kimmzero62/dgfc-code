"""정적 HTML 대시보드 한 페이지 생성 (GitHub Pages 게시용).

해석 문장은 넣지 않는다. 값, 변화, 통계, 기준 초과 사실만 표시한다.
"""
from __future__ import annotations

import json
from html import escape
from pathlib import Path

import pandas as pd

from .detect import unit_of_change

STATUS_ORDER = {"flag": 0, "error": 1, "ok": 2, "insufficient": 3, "no_data": 4}


def _num(x, dec=2, sign=False):
    if x is None or pd.isna(x):
        return "–"
    if abs(x) < 0.5 * 10 ** -dec:  # -0.0 방지
        x = 0.0
    return f"{x:+,.{dec}f}" if sign else f"{x:,.{dec}f}"


def _state(row) -> str:
    res, fetch = row["res"], row["fetch"]
    if res.flags:
        return "flag"
    if not fetch["ok"] and res.status == "no_data":
        return "error"
    return res.status


def _row_html(i: int, row) -> str:
    ind, res, fetch = row["ind"], row["res"], row["fetch"]
    dec = int(ind.get("decimals", 2))
    kind = ind.get("change", "abs")
    cu = unit_of_change(kind, ind.get("unit", ""))
    cdec = 1 if kind in ("bp", "pct") else dec
    state = _state(row)

    badges = []
    for f in res.flags:
        badges.append(f'<span class="badge flag">⚑ {escape(f.text)}</span>')
    if not fetch["ok"]:
        badges.append(f'<span class="badge err" title="{escape(fetch["error"])}">✕ 수집 오류: '
                      f'{escape(fetch["error"][:90])}</span>')
    if res.status == "insufficient":
        badges.append(f'<span class="badge muted">데이터 부족 (1년 창 {res.obs_in_window}개 관측)</span>')
    if res.status == "no_data" and fetch["ok"]:
        badges.append('<span class="badge muted">데이터 없음</span>')
    if res.stale:
        badges.append(f'<span class="badge warn">◷ 마지막 관측 후 {res.days_since}일</span>')

    rng = "–" if res.lo is None else f"{_num(res.lo, dec)} ~ {_num(res.hi, dec)}"
    z = "–" if res.z is None else _num(res.z, 2, sign=True)
    pct = "–" if res.pct_rank is None else f"{res.pct_rank:.0f}"
    return f"""
<tr class="row {state}" data-idx="{i}" tabindex="0" aria-expanded="false">
  <td class="name"><span class="caret">▸</span>{escape(ind['name'])}<div class="grp">{escape(ind['group'])}</div></td>
  <td class="num">{_num(res.value, dec)} <span class="unit">{escape(ind.get('unit', ''))}</span></td>
  <td class="date">{res.last_date or '–'}</td>
  <td class="num">{_num(res.chg1, cdec, True)}<span class="unit">{escape(cu) if res.chg1 is not None else ''}</span></td>
  <td class="num">{_num(res.chg5, cdec, True)}<span class="unit">{escape(cu) if res.chg5 is not None else ''}</span></td>
  <td class="num">{z}</td>
  <td class="num">{pct}</td>
  <td class="num rng">{rng}</td>
  <td class="badges">{''.join(badges)}</td>
</tr>
<tr class="chart-row" data-for="{i}" hidden><td colspan="9"><div class="chart" id="chart-{i}"></div></td></tr>"""


def write(rows: list[dict], cfg: dict, now, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    order = sorted(range(len(rows)), key=lambda k: (STATUS_ORDER.get(_state(rows[k]), 9),
                                                    0 if _state(rows[k]) == "flag" else k))
    charts = []
    for k in range(len(rows)):
        s = rows[k]["series"]
        if not s.empty:
            s = s[s.index > s.index[-1] - pd.Timedelta(days=cfg["defaults"]["lookback_days"])]
        charts.append({
            "name": rows[k]["ind"]["name"], "unit": rows[k]["ind"].get("unit", ""),
            "dec": int(rows[k]["ind"].get("decimals", 2)),
            "d": [d.strftime("%Y-%m-%d") for d in s.index], "v": [round(float(v), 6) for v in s.values],
        })

    n_flag = sum(1 for r in rows if r["res"].flags)
    n_err = sum(1 for r in rows if not r["fetch"]["ok"])
    flagged = [r["ind"]["name"] for r in rows if r["res"].flags]
    d = cfg["defaults"]
    body_rows = "".join(_row_html(k, rows[k]) for k in order)
    data_json = json.dumps(charts, ensure_ascii=False).replace("</", "<\\/")
    summary = (f"플래그 {n_flag}개 지표" + (f": {escape(', '.join(flagged))}" if flagged else "")
               + (f" · 수집 오류 {n_err}개" if n_err else ""))

    html = TEMPLATE.format(
        updated=f"{now:%Y-%m-%d %H:%M} KST", summary=summary, rows=body_rows, data=data_json,
        z=d["z_threshold"], cz=d["change_z_threshold"], lb=d["lookback_days"],
    )
    (out / "index.html").write_text(html, encoding="utf-8")


TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>매크로 모니터</title>
<style>
:root {{
  color-scheme: light;
  --bg: #fcfcfb; --surface: #ffffff; --line: #e4e3df; --grid: #eeede9;
  --text: #0b0b0b; --text-2: #52514e; --muted: #8a8984;
  --series: #2a78d6; --critical: #d03b3b; --warning: #b57900; --row-flag: #fdf1f1;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    color-scheme: dark;
    --bg: #141413; --surface: #1a1a19; --line: #33332f; --grid: #2a2a27;
    --text: #f0efec; --text-2: #c3c2b7; --muted: #8f8e86;
    --series: #3987e5; --critical: #e66767; --warning: #fab219; --row-flag: #2b1d1d;
  }}
}}
:root[data-theme="dark"] {{
  color-scheme: dark;
  --bg: #141413; --surface: #1a1a19; --line: #33332f; --grid: #2a2a27;
  --text: #f0efec; --text-2: #c3c2b7; --muted: #8f8e86;
  --series: #3987e5; --critical: #e66767; --warning: #fab219; --row-flag: #2b1d1d;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text);
  font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif; }}
main {{ max-width: 1280px; margin: 0 auto; padding: 20px 16px 48px; }}
h1 {{ font-size: 20px; margin: 0 0 4px; }}
.meta {{ color: var(--text-2); margin: 0 0 4px; }}
.summary {{ font-weight: 600; margin: 8px 0 16px; }}
.wrap {{ overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 8px; }}
table {{ border-collapse: collapse; width: 100%; min-width: 980px; }}
th, td {{ padding: 8px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
th {{ font-size: 12px; color: var(--text-2); font-weight: 600; position: sticky; top: 0; background: var(--surface); }}
td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
td.date {{ white-space: nowrap; color: var(--text-2); font-variant-numeric: tabular-nums; }}
.unit {{ color: var(--muted); font-size: 12px; margin-left: 2px; }}
.grp {{ color: var(--muted); font-size: 12px; }}
td.name {{ min-width: 190px; }}
tr.row {{ cursor: pointer; }}
tr.row:hover, tr.row:focus {{ outline: none; background: color-mix(in srgb, var(--series) 6%, transparent); }}
tr.row.flag {{ background: var(--row-flag); }}
.caret {{ display: inline-block; width: 14px; color: var(--muted); transition: transform .15s; }}
tr.row[aria-expanded="true"] .caret {{ transform: rotate(90deg); }}
.badges {{ min-width: 240px; }}
.badge {{ display: inline-block; margin: 0 4px 4px 0; padding: 1px 7px; border-radius: 10px; font-size: 12px;
  border: 1px solid var(--line); color: var(--text-2); }}
.badge.flag {{ border-color: var(--critical); color: var(--text); }}
.badge.flag::first-letter {{ color: var(--critical); }}
.badge.err {{ border-color: var(--critical); color: var(--critical); }}
.badge.warn {{ border-color: var(--warning); }}
.chart {{ position: sticky; left: 0; height: 240px; }}
.chart svg {{ width: 100%; height: 100%; display: block; }}
.tip {{ position: absolute; pointer-events: none; background: var(--surface); border: 1px solid var(--line);
  border-radius: 6px; padding: 4px 8px; font-size: 12px; white-space: nowrap; box-shadow: 0 2px 6px rgba(0,0,0,.12); }}
.tip strong {{ font-variant-numeric: tabular-nums; }}
.legend {{ color: var(--text-2); font-size: 12px; margin-top: 16px; }}
.legend p {{ margin: 2px 0; }}
</style>
</head>
<body>
<main>
  <h1>매크로 모니터</h1>
  <p class="meta">갱신 {updated} · 행을 누르면 최근 1년 차트가 열립니다.</p>
  <p class="summary">{summary}</p>
  <div class="wrap">
  <table>
    <thead><tr>
      <th>지표</th><th class="num">값</th><th>기준일</th><th class="num">직전 대비</th><th class="num">5영업일</th>
      <th class="num">z (1년)</th><th class="num">백분위</th><th class="num">1년 범위</th><th>표시</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
  </div>
  <div class="legend">
    <p>⚑ 플래그 기준: 1년 z-score 절댓값 ≥ {z} · 1년 고점/저점 갱신 · 직전 대비 또는 5영업일 변화가 과거 1년 변화 분포 대비 |z| ≥ {cz}. 계산 창 {lb}일.</p>
    <p>기준일은 각 지표의 마지막 관측일입니다. 주간·지연 발표 지표는 다른 지표와 기준일이 다를 수 있습니다. ◷ 표시는 마지막 관측 후 경과일입니다.</p>
    <p>금리·스프레드 변화는 bp, 가격 변화는 %, 그 외는 원 단위로 표시합니다. 기준값은 config.yaml에서 조정합니다.</p>
  </div>
</main>
<script>
const DATA = {data};
const NS = "http://www.w3.org/2000/svg";
function el(tag, attrs, parent) {{
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}}
function fmt(v, dec) {{ return v.toLocaleString("ko-KR", {{minimumFractionDigits: dec, maximumFractionDigits: dec}}); }}
function draw(idx) {{
  const box = document.getElementById("chart-" + idx);
  if (box.dataset.drawn) return;
  box.dataset.drawn = "1";
  const c = DATA[idx];
  if (!c.v.length) {{ box.textContent = "표시할 데이터가 없습니다."; return; }}
  // 표가 가로 스크롤될 때도 차트는 보이는 폭에 맞춘다
  box.style.width = (document.querySelector(".wrap").clientWidth - 22) + "px";
  const W = box.clientWidth || 800, H = 240, m = {{l: 56, r: 16, t: 12, b: 26}};
  const svg = el("svg", {{viewBox: `0 0 ${{W}} ${{H}}`, role: "img", "aria-label": c.name + " 최근 1년"}}, box);
  const t = c.d.map(s => new Date(s + "T00:00:00").getTime());
  const t0 = t[0], t1 = t[t.length - 1] || t0 + 1;
  let lo = Math.min(...c.v), hi = Math.max(...c.v);
  if (lo === hi) {{ lo -= 1; hi += 1; }}
  const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
  const X = v => m.l + (t1 === t0 ? 0 : (v - t0) / (t1 - t0)) * (W - m.l - m.r);
  const Y = v => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
  const css = getComputedStyle(document.documentElement);
  const col = n => css.getPropertyValue(n).trim();
  for (let i = 0; i <= 4; i++) {{
    const v = lo + (hi - lo) * i / 4, y = Y(v);
    el("line", {{x1: m.l, x2: W - m.r, y1: y, y2: y, stroke: col("--grid"), "stroke-width": 1}}, svg);
    const tx = el("text", {{x: m.l - 6, y: y + 4, "text-anchor": "end", "font-size": 11, fill: col("--muted")}}, svg);
    tx.textContent = fmt(v, Math.min(c.dec, 2));
  }}
  const months = new Set();
  c.d.forEach((s, i) => {{
    const key = s.slice(0, 7);
    if (months.has(key) || s.slice(5, 7) % 2) return;
    months.add(key);
    const tx = el("text", {{x: X(t[i]), y: H - 8, "text-anchor": "middle", "font-size": 11, fill: col("--muted")}}, svg);
    tx.textContent = s.slice(2, 7).replace("-", ".");
  }});
  const path = c.v.map((v, i) => (i ? "L" : "M") + X(t[i]).toFixed(1) + " " + Y(v).toFixed(1)).join("");
  el("path", {{d: path, fill: "none", stroke: col("--series"), "stroke-width": 2, "stroke-linejoin": "round"}}, svg);
  const n = c.v.length - 1;
  el("circle", {{cx: X(t[n]), cy: Y(c.v[n]), r: 4, fill: col("--series"), stroke: col("--surface"), "stroke-width": 2}}, svg);
  const hair = el("line", {{y1: m.t, y2: H - m.b, stroke: col("--muted"), "stroke-width": 1, visibility: "hidden"}}, svg);
  const dot = el("circle", {{r: 4, fill: col("--series"), stroke: col("--surface"), "stroke-width": 2, visibility: "hidden"}}, svg);
  const tip = document.createElement("div"); tip.className = "tip"; tip.hidden = true; box.appendChild(tip);
  const hit = el("rect", {{x: m.l, y: 0, width: W - m.l - m.r, height: H, fill: "transparent"}}, svg);
  hit.addEventListener("pointermove", ev => {{
    const r = svg.getBoundingClientRect();
    const px = (ev.clientX - r.left) * W / r.width;
    const tv = t0 + (px - m.l) / (W - m.l - m.r) * (t1 - t0);
    let k = 0, best = Infinity;
    for (let i = 0; i < t.length; i++) {{ const dd = Math.abs(t[i] - tv); if (dd < best) {{ best = dd; k = i; }} }}
    const x = X(t[k]), y = Y(c.v[k]);
    hair.setAttribute("x1", x); hair.setAttribute("x2", x); hair.setAttribute("visibility", "visible");
    dot.setAttribute("cx", x); dot.setAttribute("cy", y); dot.setAttribute("visibility", "visible");
    tip.replaceChildren();
    const b = document.createElement("strong"); b.textContent = fmt(c.v[k], c.dec) + " " + c.unit;
    tip.append(b, document.createTextNode("  " + c.d[k]));
    tip.hidden = false;
    const left = x * r.width / W;
    tip.style.left = Math.min(left + 10, r.width - tip.offsetWidth - 4) + "px";
    tip.style.top = "6px";
  }});
  hit.addEventListener("pointerleave", () => {{
    hair.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); tip.hidden = true;
  }});
}}
document.querySelectorAll("tr.row").forEach(tr => {{
  const toggle = () => {{
    const cr = document.querySelector(`tr.chart-row[data-for="${{tr.dataset.idx}}"]`);
    const open = cr.hidden;
    cr.hidden = !open;
    tr.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) draw(+tr.dataset.idx);
  }};
  tr.addEventListener("click", toggle);
  tr.addEventListener("keydown", e => {{ if (e.key === "Enter" || e.key === " ") {{ e.preventDefault(); toggle(); }} }});
}});
</script>
</body>
</html>
"""
