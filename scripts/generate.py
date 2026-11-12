#!/usr/bin/env python3
"""Generate the animated "stock ticker" SVG cards for the profile README.

Price  = contributions in the last 30 days (shown in cents: 30 -> $0.30)
Candle = one week: open = 30-day total at the end of the previous week,
         close = 30-day total at the end of this week, high/low = daily extremes
Volume = contributions made during that week

Usage:
  GITHUB_TOKEN=... python scripts/generate.py            # live data (used by the Action)
  python scripts/generate.py --demo                      # offline sample data
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import math
import os
import random
import sys
import urllib.request
from html import escape
from pathlib import Path

USER = os.environ.get("GH_USER", "AndrewIsaCoder")
TICKER = os.environ.get("TICKER", "ANDRE")
WEEKS = 52
OUT = Path(__file__).resolve().parent.parent / "assets"

LANG_COLORS = {
    "Python": "#3572A5", "HTML": "#e34c26", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "Jupyter Notebook": "#DA5B0B", "R": "#198CE7", "CSS": "#663399", "Java": "#b07219",
    "C++": "#f34b7d", "C": "#555555", "C#": "#178600", "SQL": "#e38c00", "Shell": "#89e051",
    "Vue": "#41b883", "PHP": "#4F5D95", "Go": "#00ADD8", "Rust": "#dea584", "Kotlin": "#A97BFF",
}

GREEN, RED, MUTED, TEXT, GRID = "#26a69a", "#ef5350", "#8b949e", "#e6edf3", "#1c2128"
MA_FAST, MA_SLOW = "#f0b90b", "#2f81f7"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,monospace"


# ----------------------------------------------------------------------------- data
QUERY = """
query($login:String!, $f1:DateTime!, $t1:DateTime!, $f2:DateTime!, $t2:DateTime!) {
  user(login:$login) {
    name login bio avatarUrl(size:200)
    followers { totalCount }
    repositories(first:100, ownerAffiliations:OWNER, privacy:PUBLIC, isFork:false,
                 orderBy:{field:PUSHED_AT, direction:DESC}) {
      totalCount
      nodes { name stargazerCount primaryLanguage { name } }
    }
    a: contributionsCollection(from:$f1, to:$t1) {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
    b: contributionsCollection(from:$f2, to:$t2) {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
  }
}"""


def fetch_live() -> dict:
    token = os.environ["GITHUB_TOKEN"]
    now = dt.datetime.now(dt.timezone.utc)
    mid = now - dt.timedelta(days=300)            # each collection may span at most 1 year
    start = now - dt.timedelta(days=WEEKS * 7 + 45)
    iso = lambda t: t.replace(microsecond=0).isoformat()  # noqa: E731
    body = json.dumps({"query": QUERY, "variables": {
        "login": USER, "f1": iso(start), "t1": iso(mid), "f2": iso(mid), "t2": iso(now)}}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=body, headers={
        "Authorization": f"bearer {token}", "Content-Type": "application/json",
        "User-Agent": "readme-ticker"})
    data = json.load(urllib.request.urlopen(req))
    if "errors" in data:
        raise SystemExit(data["errors"])
    u = data["data"]["user"]
    days: dict[str, int] = {}
    for key in ("a", "b"):
        for w in u[key]["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                days[d["date"]] = d["contributionCount"]
    repos = u["repositories"]["nodes"]
    return {
        "name": u["name"] or u["login"], "login": u["login"], "bio": u["bio"] or "",
        "avatar": u["avatarUrl"], "followers": u["followers"]["totalCount"],
        "repo_count": u["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos),
        "repos": [{"name": r["name"], "stars": r["stargazerCount"],
                   "lang": (r["primaryLanguage"] or {}).get("name")} for r in repos],
        "days": days,
    }


def fetch_demo() -> dict:
    rnd = random.Random(11)
    today = dt.date.today()
    days = {}
    for i in range(WEEKS * 7 + 45):
        d = today - dt.timedelta(days=i)
        season = 1.2 + math.sin(i / 38) + (2.5 if 55 <= i <= 75 else 0) + (1.5 if 200 <= i <= 230 else 0)
        days[d.isoformat()] = rnd.randint(0, 3) * (rnd.random() < 0.22 * season) + \
            (rnd.random() < 0.05) * rnd.randint(3, 9)
    langs = ["HTML", "Python", "Vue", "Jupyter Notebook", "JavaScript", "R", "Python"]
    names = ["Furdeco-Furniture", "HairIT", "TodoApp", "Jupyter-Analyze-Data",
             "Portfolio", "R-Statistics", "SQL-Playground"]
    return {
        "name": "Stoian Andrei", "login": USER,
        "bio": "Young software developer passionate about coding, with experience in "
               "Python, SQL, R, and more. I enjoy exploring new technologies.",
        "avatar": f"https://avatars.githubusercontent.com/{USER}?s=200",
        "followers": 1, "repo_count": 21, "stars": 3,
        "repos": [{"name": n, "stars": s, "lang": l}
                  for n, s, l in zip(names, [1, 0, 0, 1, 0, 1, 0], langs)],
        "days": days,
    }


def avatar_data_uri(url: str) -> str:
    """GitHub's image proxy blocks external images inside SVGs, so inline it."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "readme-ticker"})
        resp = urllib.request.urlopen(req, timeout=15)
        mime = resp.headers.get_content_type() or "image/png"
        return f"data:{mime};base64," + base64.b64encode(resp.read()).decode()
    except Exception:  # noqa: BLE001 - avatar is cosmetic
        return ""


# ----------------------------------------------------------------------------- math
def candles(days: dict[str, int]) -> list[dict]:
    today = dt.date.today()
    count = lambda d: days.get(d.isoformat(), 0)  # noqa: E731
    rolling = lambda d: sum(count(d - dt.timedelta(days=k)) for k in range(30))  # noqa: E731
    out = []
    for w in range(WEEKS - 1, -1, -1):
        end = today - dt.timedelta(days=7 * w)
        week = [end - dt.timedelta(days=k) for k in range(6, -1, -1)]
        vals = [rolling(d) for d in week]
        o = rolling(week[0] - dt.timedelta(days=1))
        out.append({"o": o, "c": vals[-1], "h": max(vals + [o]), "l": min(vals + [o]),
                    "v": sum(count(d) for d in week), "date": end})
    return out


def sma(vals: list[float], n: int) -> list[float | None]:
    return [None if i + 1 < n else sum(vals[i + 1 - n:i + 1]) / n for i in range(len(vals))]


def nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    raw = (hi - lo) / n or 1
    mag = 10 ** math.floor(math.log10(raw))
    step = next(s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw)
    t = math.ceil(lo / step) * step
    out = []
    while t <= hi + 1e-9:
        out.append(t)
        t += step
    return out


def money(c: float) -> str:
    return f"${c / 100:,.2f}"


def px(c: float) -> str:
    return f"{c / 100:.2f}"


# ----------------------------------------------------------------------------- svg
def ticker_svg(p: dict, avatar: str) -> str:
    W, H = 860, 610
    cs = candles(p["days"])
    N = len(cs)
    last = cs[-1]
    price = last["c"]
    prev = cs[-2]["c"] if N > 1 else last["o"]
    chg = price - prev
    chg_pct = chg / prev * 100 if prev else 0.0
    up = chg >= 0
    col_chg = GREEN if up else RED
    top_lang = next((r["lang"] for r in p["repos"] if r["lang"]), "Code")
    lang_col = LANG_COLORS.get(top_lang, "#f0883e")

    # ---- geometry
    cx0, cx1 = 24, W - 76            # plot area; price axis to the right
    cy0, cy1 = 176, 396              # candles
    vy0, vy1 = 404, 452              # volume
    ax_y = 468                       # date axis labels
    hi = max(c["h"] for c in cs)
    lo = min(c["l"] for c in cs)
    pad = max((hi - lo) * 0.08, 1)
    lo_p, hi_p = max(lo - pad, 0), hi + pad
    y = lambda v: cy1 - (v - lo_p) / (hi_p - lo_p) * (cy1 - cy0)  # noqa: E731
    step = (cx1 - cx0) / N
    bw = max(step * 0.66, 2)
    xc = lambda i: cx0 + i * step + step / 2  # noqa: E731
    vmax = max(max(c["v"] for c in cs), 1)

    # ---- grid + price axis
    grid = []
    for t in nice_ticks(lo_p, hi_p, 7):
        gy = y(t)
        if cy0 - 1 <= gy <= cy1 + 1:
            grid.append(f'<line x1="{cx0}" x2="{cx1}" y1="{gy:.1f}" y2="{gy:.1f}" stroke="{GRID}"/>'
                        f'<text x="{cx1 + 8}" y="{gy + 3.5:.1f}" class="ax">{px(t)}</text>')
    seen_month = None
    for i, c in enumerate(cs):
        m = c["date"].strftime("%b")
        if m != seen_month:
            if seen_month is not None:
                grid.append(f'<line x1="{xc(i):.1f}" x2="{xc(i):.1f}" y1="{cy0}" y2="{vy1}" stroke="{GRID}"/>'
                            f'<text x="{xc(i):.1f}" y="{ax_y}" class="ax" text-anchor="middle">'
                            f'{m if m != "Jan" else c["date"].strftime("%Y")}</text>')
            seen_month = m
    grid.append(f'<line x1="{cx0}" x2="{cx1}" y1="{vy0 - 4}" y2="{vy0 - 4}" stroke="#30363d"/>')
    grid.append(f'<line x1="{cx0}" x2="{cx1}" y1="{vy1}" y2="{vy1}" stroke="#30363d"/>')
    grid.append(f'<line x1="{cx1}" x2="{cx1}" y1="{cy0}" y2="{vy1}" stroke="#30363d"/>')

    # ---- candles + volume
    bars = []
    for i, c in enumerate(cs):
        x = xc(i) - bw / 2
        bull = c["c"] >= c["o"]
        col = GREEN if bull else RED
        yt, yb = y(max(c["o"], c["c"])), y(min(c["o"], c["c"]))
        hgt = max(yb - yt, 1.2)
        d = 0.1 + i * 0.025
        cls = "cd last" if i == N - 1 else "cd"
        bars.append(
            f'<g class="{cls}" style="animation-delay:{d:.3f}s">'
            f'<line x1="{xc(i):.1f}" x2="{xc(i):.1f}" y1="{y(c["h"]):.1f}" y2="{y(c["l"]):.1f}" stroke="{col}"/>'
            f'<rect x="{x:.1f}" y="{yt:.1f}" width="{bw:.1f}" height="{hgt:.1f}" fill="{col}"/></g>')
        vh = max(c["v"] / vmax * (vy1 - vy0), 0.8)
        bars.append(f'<rect class="vol" style="animation-delay:{d + .2:.3f}s" x="{x:.1f}" y="{vy1 - vh:.1f}" '
                    f'width="{bw:.1f}" height="{vh:.1f}" fill="{col}" fill-opacity=".45"/>')

    # ---- moving averages
    closes = [c["c"] for c in cs]
    ma_paths = []
    for n, colr in ((4, MA_FAST), (12, MA_SLOW)):
        pts = [f"{xc(i):.1f},{y(v):.1f}" for i, v in enumerate(sma(closes, n)) if v is not None]
        if len(pts) > 1:
            ma_paths.append(f'<polyline class="ma" pathLength="1" points="{" ".join(pts)}" fill="none" '
                            f'stroke="{colr}" stroke-width="1.4" stroke-linejoin="round"/>')
    ma4, ma12 = sma(closes, 4)[-1], sma(closes, 12)[-1]

    # ---- crosshair that hops across the candles (CSS only, loops forever)
    dt_hop = 0.32
    cycle = N * dt_hop
    share = 100 / N
    hops = []
    for i, c in enumerate(cs):
        cx = xc(i)
        cyv = y(c["c"])
        col = GREEN if c["c"] >= c["o"] else RED
        tx = cx + 12 if cx < cx1 - 150 else cx - 142
        hops.append(
            f'<g class="hop" style="animation-delay:{2.2 + i * dt_hop:.2f}s">'
            f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{cy0}" y2="{vy1}" class="xh"/>'
            f'<line x1="{cx0}" x2="{cx1}" y1="{cyv:.1f}" y2="{cyv:.1f}" class="xh"/>'
            f'<rect x="{cx1}" y="{cyv - 9:.1f}" width="52" height="18" fill="#363c44"/>'
            f'<text x="{cx1 + 8}" y="{cyv + 3.5:.1f}" class="ax" fill="{TEXT}">{px(c["c"])}</text>'
            f'<rect x="{cx - 34:.1f}" y="{vy1 + 4}" width="68" height="16" rx="2" fill="#363c44"/>'
            f'<text x="{cx:.1f}" y="{vy1 + 15}" class="ax" text-anchor="middle" fill="{TEXT}">{c["date"]:%d %b %y}</text>'
            f'<g transform="translate({tx:.1f},{cy0 + 8})">'
            f'<rect width="130" height="74" rx="4" fill="#161b22" fill-opacity=".94" stroke="#30363d"/>'
            f'<text x="10" y="17" class="tt" fill="{MUTED}">WEEK OF {c["date"] - dt.timedelta(days=6):%d %b}</text>'
            f'<text x="10" y="33" class="tt">O <tspan fill="{col}">{px(c["o"])}</tspan>  H <tspan fill="{col}">{px(c["h"])}</tspan></text>'
            f'<text x="10" y="48" class="tt">L <tspan fill="{col}">{px(c["l"])}</tspan>  C <tspan fill="{col}">{px(c["c"])}</tspan></text>'
            f'<text x="10" y="63" class="tt">Vol <tspan fill="{col}">{c["v"]}</tspan> commits</text>'
            f'</g></g>')

    # ---- current price line + tag
    py = y(price)
    lx = xc(N - 1)

    # ---- stats strip
    total_y = sum(c["v"] for c in cs)
    avg_v = total_y / N
    stats = [
        ("OPEN", px(last["o"])), ("HIGH", px(last["h"])), ("LOW", px(last["l"])),
        ("52W HIGH", px(hi)), ("52W LOW", px(lo)), ("AVG VOL", f"{avg_v:.1f}"),
        ("1Y VOLUME", f"{total_y:,}"), ("REPOS", str(p["repo_count"])), ("STARS", f"★ {p['stars']}"),
    ]
    sw = (W - 48) / len(stats)
    stats_svg = "".join(
        f'<g transform="translate({24 + k * sw:.1f},492)">'
        f'<text class="sl">{lab}</text><text y="18" class="sv">{escape(val)}</text></g>'
        for k, (lab, val) in enumerate(stats))

    # ---- scrolling tape
    tape_items, tx = [], 0.0
    for r in p["repos"][:12]:
        lc = LANG_COLORS.get(r["lang"] or "", MUTED)
        label = escape(r["name"].upper()[:18])
        ab = escape((r["lang"] or "?")[0].upper())
        tw = 24 + (len(r["name"][:18]) + 2 + len(str(r["stars"]))) * 8.4
        tape_items.append(
            f'<g transform="translate({tx:.0f},0)"><rect x="0" y="-9" width="16" height="16" rx="3" fill="{lc}"/>'
            f'<text x="8" y="3" font-size="10" font-weight="700" text-anchor="middle" fill="#0d1117">{ab}</text>'
            f'<text x="24" y="4" class="tape">{label} <tspan fill="{GREEN}">★{r["stars"]}</tspan></text>'
            f'<rect x="{tw + 14:.0f}" y="-2" width="4" height="4" fill="#484f58"/></g>')
        tx += tw + 40
    tape = "".join(tape_items)
    tape_w = max(tx, 1)

    av = (f'<clipPath id="av"><circle cx="58" cy="50" r="22"/></clipPath>'
          f'<image href="{avatar}" x="36" y="28" width="44" height="44" clip-path="url(#av)"/>'
          if avatar else "")
    sign = "+" if up else "−"
    tfs = "".join(
        f'<g transform="translate({24 + k * 40},128)"><rect width="34" height="22" rx="4" '
        f'fill="{"#2f81f7" if t == "1Y" else "#161b22"}" fill-opacity="{".25" if t == "1Y" else "1"}" '
        f'stroke="{"#2f81f7" if t == "1Y" else "#30363d"}"/><text x="17" y="15" class="tf" text-anchor="middle" '
        f'fill="{TEXT if t == "1Y" else MUTED}">{t}</text></g>'
        for k, t in enumerate(["1M", "3M", "6M", "1Y", "ALL"]))
    badge_x = 98 + (len(TICKER) + 1) * 19 + 10

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">
<style>
.ax{{font-family:{MONO};font-size:10px;fill:{MUTED}}}
.tt{{font-family:{MONO};font-size:10.5px;fill:{TEXT}}}
.tf{{font-family:{MONO};font-size:10px;font-weight:700}}
.sl{{font-family:{MONO};font-size:9px;fill:{MUTED};letter-spacing:1px}}
.sv{{font-family:{MONO};font-size:13px;font-weight:700;fill:{TEXT}}}
.tape{{font-family:{MONO};font-size:13px;font-weight:700;fill:{TEXT};letter-spacing:.5px}}
.cd{{transform-box:fill-box;transform-origin:bottom;opacity:0;animation:rise .5s cubic-bezier(.2,.9,.3,1.2) forwards}}
.vol{{transform-box:fill-box;transform-origin:bottom;opacity:0;animation:rise .45s ease-out forwards}}
@keyframes rise{{from{{opacity:0;transform:scaleY(0)}}to{{opacity:1;transform:scaleY(1)}}}}
.last rect{{animation:tick 1.4s ease-in-out 2s infinite}}
@keyframes tick{{50%{{opacity:.5}}}}
.ma{{stroke-dasharray:1;stroke-dashoffset:1;animation:draw 1.6s ease-out 1.2s forwards}}
@keyframes draw{{to{{stroke-dashoffset:0}}}}
.xh{{stroke:#8b949e;stroke-opacity:.55;stroke-dasharray:3 3}}
.hop{{opacity:0;animation:hop {cycle:.2f}s linear infinite}}
@keyframes hop{{0%,{share:.3f}%{{opacity:1}}{share + 0.001:.3f}%,100%{{opacity:0}}}}
.pulse{{transform-box:fill-box;transform-origin:center;animation:ping 1.6s ease-out infinite}}
@keyframes ping{{from{{transform:scale(1);opacity:.8}}to{{transform:scale(3.4);opacity:0}}}}
.blink{{animation:blink 1.2s steps(2,start) infinite}}
@keyframes blink{{to{{visibility:hidden}}}}
.dash{{stroke-dasharray:2 3;animation:dash 1s linear infinite}}
@keyframes dash{{to{{stroke-dashoffset:-5}}}}
.roll{{animation:roll {tape_w / 45:.1f}s linear infinite}}
@keyframes roll{{to{{transform:translateX(-{tape_w:.0f}px)}}}}
.fade{{opacity:0;animation:fade .7s ease forwards}}
@keyframes fade{{to{{opacity:1}}}}
.ring{{transform-box:fill-box;transform-origin:center;animation:spin 8s linear infinite}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
.flash{{animation:flash 2.8s ease-in-out infinite}}
@keyframes flash{{0%,100%{{fill-opacity:.12}}50%{{fill-opacity:.3}}}}
</style>
<defs>
<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0d1117"/><stop offset="1" stop-color="#090c10"/></linearGradient>
<clipPath id="tapeclip"><rect x="1" y="{H - 50}" width="{W - 2}" height="40"/></clipPath>
<clipPath id="plot"><rect x="{cx0}" y="{cy0 - 4}" width="{cx1 - cx0}" height="{cy1 - cy0 + 8}"/></clipPath>
</defs>
<rect width="{W}" height="{H}" rx="12" fill="url(#bg)" stroke="#30363d"/>

<g class="fade">
  <circle class="ring" cx="58" cy="50" r="25.5" fill="none" stroke="{GREEN}" stroke-width="2" stroke-dasharray="28 8"/>
  {av}
  <text x="98" y="48" font-size="26" font-weight="800" fill="{TEXT}">${escape(TICKER)}</text>
  <g transform="translate({badge_x},29)">
    <rect width="{104 + len(top_lang) * 7}" height="22" rx="11" fill="{lang_col}" fill-opacity=".14" stroke="{lang_col}" stroke-opacity=".8"/>
    <text x="12" y="15" font-family="{MONO}" font-size="9.5" font-weight="700" fill="{lang_col}" letter-spacing="1.5">SECTOR · {escape(top_lang.upper())}</text>
  </g>
  <text x="98" y="70" font-size="12" fill="{MUTED}">{escape(p["name"])} · GITHUB: {escape(TICKER)} · Delayed ≤6h · USD</text>

  <text x="24" y="108" font-size="34" font-weight="800" fill="{TEXT}">{money(price)}</text>
  <rect x="{36 + len(money(price)) * 19}" y="84" width="150" height="28" rx="6" fill="{col_chg}" class="flash"/>
  <text x="{48 + len(money(price)) * 19}" y="103" font-family="{MONO}" font-size="13" font-weight="700" fill="{col_chg}">{"▲" if up else "▼"} {sign}{abs(chg) / 100:.2f} ({sign}{abs(chg_pct):.2f}%)</text>

  <g transform="translate({W - 24},44)">
    <text text-anchor="end" font-family="{MONO}" font-size="10" fill="{MUTED}">{dt.date.today():%a %d %b %Y}</text>
    <circle cx="-92" cy="18" r="4" fill="{GREEN}" class="pulse"/><circle cx="-92" cy="18" r="4" fill="{GREEN}"/>
    <text y="22" text-anchor="end" font-family="{MONO}" font-size="11" font-weight="700" fill="{GREEN}" letter-spacing="1">MARKET OPEN</text>
    <text y="58" text-anchor="end" font-family="{MONO}" font-size="10" fill="{MUTED}">price = commits · last 30 days</text>
  </g>
</g>

{tfs}
<text x="{24 + 5 * 40 + 8}" y="143" font-family="{MONO}" font-size="10" fill="{MUTED}">· 1W candles</text>
<g font-family="{MONO}" font-size="10.5">
  <text x="{cx0 + 2}" y="168" fill="{MUTED}">{escape(TICKER)} · 1W · GH  O<tspan fill="{col_chg}">{px(last["o"])}</tspan> H<tspan fill="{col_chg}">{px(last["h"])}</tspan> L<tspan fill="{col_chg}">{px(last["l"])}</tspan> C<tspan fill="{col_chg}">{px(last["c"])}</tspan> Vol <tspan fill="{col_chg}">{last["v"]}</tspan></text>
  <text x="{cx1 - 2}" y="168" text-anchor="end"><tspan fill="{MA_FAST}">MA 4  {px(ma4 or 0)}</tspan>   <tspan fill="{MA_SLOW}">MA 12  {px(ma12 or 0)}</tspan></text>
</g>

{"".join(grid)}
{"".join(bars)}
<g clip-path="url(#plot)">{"".join(ma_paths)}</g>

<line x1="{cx0}" x2="{cx1}" y1="{py:.1f}" y2="{py:.1f}" stroke="{col_chg}" stroke-opacity=".8" class="dash"/>
<g transform="translate({lx:.1f},{py:.1f})"><circle r="3.5" fill="{col_chg}" class="pulse"/></g>
{"".join(hops)}
<g class="fade" style="animation-delay:1.4s">
  <rect x="{cx1}" y="{py - 10:.1f}" width="56" height="20" fill="{col_chg}"/>
  <text x="{cx1 + 7}" y="{py + 4:.1f}" font-family="{MONO}" font-size="11" font-weight="700" fill="#fff">{px(price)}</text>
</g>
<text x="{cx1 + 8}" y="{vy0 + 8}" class="ax">VOL</text>
<text x="{cx1 + 8}" y="{vy0 + 20}" class="ax">{vmax}</text>

<line x1="1" x2="{W - 1}" y1="480" y2="480" stroke="{GRID}"/>
{stats_svg}
<text x="24" y="{H - 62}" font-family="{MONO}" font-size="9.5" fill="#484f58">Data: GitHub contribution calendar · candles: weekly O/H/L/C of the 30-day contribution total · refreshed every 6h</text>

<rect x="1" y="{H - 50}" width="{W - 2}" height="40" fill="#161b22"/>
<g clip-path="url(#tapeclip)"><g transform="translate(20,{H - 30})"><g class="roll">{tape}<g transform="translate({tape_w:.0f},0)">{tape}</g></g></g></g>
</svg>'''


def wrap(text: str, width: int) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def profile_svg(p: dict, avatar: str) -> str:
    W, H = 860, 230
    bio = wrap(p["bio"], 62)[:3]
    bio_svg = "".join(f'<text x="40" y="{128 + i * 22}" font-size="16" fill="#c9d1d9" class="fade" '
                      f'style="animation-delay:{.4 + i * .15:.2f}s">{escape(l)}</text>' for i, l in enumerate(bio))
    av = (f'<clipPath id="pav"><circle cx="{W - 120}" cy="125" r="56"/></clipPath>'
          f'<image href="{avatar}" x="{W - 176}" y="69" width="112" height="112" clip-path="url(#pav)"/>'
          if avatar else "")
    stats = f'{p["followers"]} followers · {p["repo_count"]} repositories · ★ {p["stars"]} stars'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">
<style>
.fade{{opacity:0;animation:fade .8s ease forwards}}
@keyframes fade{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:none}}}}
.ring{{transform-box:fill-box;transform-origin:center;animation:spin 10s linear infinite}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
.halo{{transform-box:fill-box;transform-origin:center;animation:halo 2.4s ease-out infinite}}
@keyframes halo{{from{{transform:scale(1);opacity:.6}}to{{transform:scale(1.25);opacity:0}}}}
.blink{{animation:blink 1.2s steps(2,start) infinite}}
@keyframes blink{{to{{visibility:hidden}}}}
</style>
<rect width="{W}" height="{H}" rx="12" fill="#0d1117" stroke="#30363d"/>
<text x="40" y="40" font-family="{MONO}" font-size="11" font-weight="700" fill="{GREEN}" letter-spacing="2"><tspan class="blink">▲</tspan> COMPANY PROFILE</text>
<line x1="1" x2="{W - 1}" y1="58" y2="58" stroke="{GRID}"/>
<text x="40" y="100" font-size="30" font-weight="800" fill="{TEXT}" class="fade">{escape(p["name"])}</text>
{bio_svg}
<text x="40" y="{140 + len(bio) * 22}" font-family="{MONO}" font-size="12" fill="{MUTED}" class="fade" style="animation-delay:.9s">{escape(stats)}</text>
<circle class="halo" cx="{W - 120}" cy="125" r="60" fill="none" stroke="{GREEN}" stroke-width="3"/>
<circle cx="{W - 120}" cy="125" r="60" fill="#161b22" stroke="{GREEN}" stroke-width="4"/>
<circle class="ring" cx="{W - 120}" cy="125" r="68" fill="none" stroke="{GREEN}" stroke-opacity=".5" stroke-width="2" stroke-dasharray="6 10"/>
{av}
</svg>'''


def main() -> None:
    demo = "--demo" in sys.argv or not os.environ.get("GITHUB_TOKEN")
    p = fetch_demo() if demo else fetch_live()
    avatar = avatar_data_uri(p["avatar"])
    OUT.mkdir(exist_ok=True)
    (OUT / "ticker.svg").write_text(ticker_svg(p, avatar), encoding="utf-8")
    (OUT / "profile.svg").write_text(profile_svg(p, avatar), encoding="utf-8")
    print(f"wrote {OUT}/ticker.svg and profile.svg ({'demo' if demo else 'live'} data)")


if __name__ == "__main__":
    main()
