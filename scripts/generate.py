#!/usr/bin/env python3
"""Generate the animated "stock ticker" SVG cards for the profile README.

Price  = contributions in the last 30 days (shown in cents: 30 -> $0.30)
Candle = one week: open = 30-day total at the end of the previous week,
         close = 30-day total at the end of this week
Volume = contributions made during that week

Usage:
  GITHUB_TOKEN=... python scripts/generate.py            # live data (used by the Action)
  python scripts/generate.py --demo                      # offline sample data
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import os
import random
import sys
import urllib.request
from html import escape
from pathlib import Path

USER = os.environ.get("GH_USER", "AndrewIsaCoder")
TICKER = os.environ.get("TICKER", "ANDRE")
WEEKS = 26
OUT = Path(__file__).resolve().parent.parent / "assets"

LANG_COLORS = {
    "Python": "#3572A5", "HTML": "#e34c26", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "Jupyter Notebook": "#DA5B0B", "R": "#198CE7", "CSS": "#663399", "Java": "#b07219",
    "C++": "#f34b7d", "C": "#555555", "C#": "#178600", "SQL": "#e38c00", "Shell": "#89e051",
    "Vue": "#41b883", "PHP": "#4F5D95", "Go": "#00ADD8", "Rust": "#dea584", "Kotlin": "#A97BFF",
}

GREEN, RED, MUTED, TEXT, GRID = "#3fb950", "#f85149", "#8b949e", "#e6edf3", "#21262d"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,monospace"


# ----------------------------------------------------------------------------- data
QUERY = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login:$login) {
    name login bio avatarUrl(size:200)
    followers { totalCount }
    repositories(first:100, ownerAffiliations:OWNER, privacy:PUBLIC, isFork:false,
                 orderBy:{field:PUSHED_AT, direction:DESC}) {
      totalCount
      nodes { name stargazerCount primaryLanguage { name color } }
    }
    contributionsCollection(from:$from, to:$to) {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
  }
}"""


def fetch_live() -> dict:
    token = os.environ["GITHUB_TOKEN"]
    to = dt.datetime.now(dt.timezone.utc)
    frm = to - dt.timedelta(days=WEEKS * 7 + 40)
    body = json.dumps({"query": QUERY, "variables": {
        "login": USER, "from": frm.isoformat(), "to": to.isoformat()}}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=body, headers={
        "Authorization": f"bearer {token}", "Content-Type": "application/json",
        "User-Agent": "readme-ticker"})
    data = json.load(urllib.request.urlopen(req))
    if "errors" in data:
        raise SystemExit(data["errors"])
    u = data["data"]["user"]
    days = {d["date"]: d["contributionCount"]
            for w in u["contributionsCollection"]["contributionCalendar"]["weeks"]
            for d in w["contributionDays"]}
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
    rnd = random.Random(7)
    today = dt.date.today()
    days = {}
    for i in range(WEEKS * 7 + 40):
        d = today - dt.timedelta(days=i)
        burst = 9 if 60 <= i <= 66 else 0
        days[d.isoformat()] = (rnd.random() < 0.18) * rnd.randint(1, 4) + burst * (rnd.random() < .8)
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


def money(c: int) -> str:
    return f"${c / 100:,.2f}"


# ----------------------------------------------------------------------------- svg
def ticker_svg(p: dict, avatar: str) -> str:
    W, H = 840, 462
    cs = candles(p["days"])
    price = cs[-1]["c"]
    base = cs[-5]["c"] if len(cs) >= 5 else cs[0]["o"]
    chg = (price - base) / base * 100 if base else 0.0
    up = chg >= 0
    top_lang = next((r["lang"] for r in p["repos"] if r["lang"]), "Code")
    lang_col = LANG_COLORS.get(top_lang, "#f0883e")

    # chart geometry
    cx0, cx1, cy0, cy1 = 40, W - 40, 110, 330
    vy0, vy1 = 340, 380
    hi = max(max(c["h"] for c in cs), 1)
    lo = min(c["l"] for c in cs)
    span = max(hi - lo, 1)
    y = lambda v: cy1 - (v - lo) / span * (cy1 - cy0)  # noqa: E731
    step = (cx1 - cx0) / len(cs)
    bw = step * 0.62
    vmax = max(max(c["v"] for c in cs), 1)

    g = []
    for i in range(5):
        gy = cy0 + i * (cy1 - cy0) / 4
        g.append(f'<line x1="{cx0}" x2="{cx1}" y1="{gy:.1f}" y2="{gy:.1f}" stroke="{GRID}"/>')

    bars = []
    for i, c in enumerate(cs):
        x = cx0 + i * step + (step - bw) / 2
        col = GREEN if c["c"] >= c["o"] else RED
        yt, yb = y(max(c["o"], c["c"])), y(min(c["o"], c["c"]))
        hgt = max(yb - yt, 2)
        d = 0.15 + i * 0.06
        last = " last" if i == len(cs) - 1 else ""
        bars.append(
            f'<g class="cd{last}" style="animation-delay:{d:.2f}s">'
            f'<line x1="{x + bw / 2:.1f}" x2="{x + bw / 2:.1f}" y1="{y(c["h"]):.1f}" '
            f'y2="{y(c["l"]):.1f}" stroke="{col}" stroke-width="1.5"/>'
            f'<rect x="{x:.1f}" y="{yt:.1f}" width="{bw:.1f}" height="{hgt:.1f}" rx="1.5" fill="{col}"/>'
            f'<title>{c["date"]:%d %b}: {money(c["o"])} → {money(c["c"])} · {c["v"]} commits</title></g>')
        vh = max(c["v"] / vmax * (vy1 - vy0), 1)
        bars.append(
            f'<rect class="vol" style="animation-delay:{d + .3:.2f}s" x="{x:.1f}" y="{vy1 - vh:.1f}" '
            f'width="{bw:.1f}" height="{vh:.1f}" fill="#30363d"/>')

    last_x = cx0 + (len(cs) - 1) * step + step / 2
    py = y(price)

    tape_items, tx = [], 0
    for r in p["repos"][:12]:
        lc = LANG_COLORS.get(r["lang"] or "", MUTED)
        label = escape(r["name"].upper()[:18])
        ab = escape((r["lang"] or "?")[0].upper())
        tw = 24 + (len(r["name"][:18]) + 2 + len(str(r["stars"]))) * 8.4
        tape_items.append(
            f'<g transform="translate({tx},0)"><rect x="0" y="-9" width="16" height="16" rx="3" fill="{lc}"/>'
            f'<text x="8" y="3" font-size="10" font-weight="700" text-anchor="middle" fill="#0d1117">{ab}</text>'
            f'<text x="24" y="4" class="tape">{label} <tspan fill="{GREEN}">★{r["stars"]}</tspan></text>'
            f'<rect x="{tw + 14:.0f}" y="-3" width="6" height="6" fill="{MUTED}"/></g>')
        tx += tw + 44
    tape = "".join(tape_items)
    tape_w = max(tx, 1)

    av = (f'<clipPath id="av"><circle cx="72" cy="56" r="22"/></clipPath>'
          f'<image href="{avatar}" x="50" y="34" width="44" height="44" clip-path="url(#av)"/>'
          if avatar else "")
    arrow = "▲" if up else "▼"
    chg_col = GREEN if up else RED

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">
<style>
.mono{{font-family:{MONO}}}
.tape{{font-family:{MONO};font-size:13px;font-weight:700;fill:{TEXT};letter-spacing:.5px}}
.cd{{transform-box:fill-box;transform-origin:bottom;opacity:0;animation:rise .6s cubic-bezier(.2,.9,.3,1.3) forwards}}
.vol{{transform-box:fill-box;transform-origin:bottom;opacity:0;animation:rise .5s ease-out forwards}}
.last rect{{animation:glow 1.6s ease-in-out 2s infinite}}
@keyframes rise{{from{{opacity:0;transform:scaleY(0)}}to{{opacity:1;transform:scaleY(1)}}}}
@keyframes glow{{50%{{opacity:.45}}}}
.pulse{{transform-box:fill-box;transform-origin:center;animation:ping 1.6s ease-out infinite}}
@keyframes ping{{from{{transform:scale(1);opacity:.8}}to{{transform:scale(3.2);opacity:0}}}}
.blink{{animation:blink 1.2s steps(2,start) infinite}}
@keyframes blink{{to{{visibility:hidden}}}}
.dash{{stroke-dasharray:4 4;animation:dash 1s linear infinite}}
@keyframes dash{{to{{stroke-dashoffset:-8}}}}
.scan{{animation:scan 6s linear 2.2s infinite;opacity:0}}
@keyframes scan{{0%{{transform:translateX(0);opacity:0}}8%{{opacity:1}}92%{{opacity:1}}100%{{transform:translateX({cx1 - cx0}px);opacity:0}}}}
.roll{{animation:roll {tape_w / 45:.1f}s linear infinite}}
@keyframes roll{{to{{transform:translateX(-{tape_w:.0f}px)}}}}
.fade{{opacity:0;animation:fade .8s ease forwards}}
@keyframes fade{{to{{opacity:1}}}}
.ring{{transform-box:fill-box;transform-origin:center;animation:spin 8s linear infinite}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
</style>
<defs>
<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0d1117"/><stop offset="1" stop-color="#0a0e14"/></linearGradient>
<linearGradient id="sc" x1="0" x2="1"><stop offset="0" stop-color="{GREEN}" stop-opacity="0"/><stop offset="1" stop-color="{GREEN}" stop-opacity=".25"/></linearGradient>
<clipPath id="tapeclip"><rect x="0" y="{H - 52}" width="{W}" height="44"/></clipPath>
</defs>
<rect width="{W}" height="{H}" rx="14" fill="url(#bg)" stroke="#30363d"/>

<g class="fade">
  <circle class="ring" cx="72" cy="56" r="25" fill="none" stroke="{GREEN}" stroke-width="2" stroke-dasharray="30 9"/>
  {av}
  <text x="108" y="64" font-size="30" font-weight="800" fill="{TEXT}">${escape(TICKER)}</text>
  <g transform="translate({108 + (len(TICKER) + 1) * 23 + 12},38)">
    <rect width="{110 + len(top_lang) * 7}" height="26" rx="13" fill="{lang_col}" fill-opacity=".15" stroke="{lang_col}"/>
    <text x="14" y="17" class="mono" font-size="10" font-weight="700" fill="{lang_col}" letter-spacing="1.5">SECTOR · {escape(top_lang.upper())}</text>
  </g>
  <text x="108" y="86" font-size="12" fill="{MUTED}">{escape(p["name"])} · GitHub · price = contributions in the last 30 days</text>

  <text x="{W - 40}" y="62" text-anchor="end" font-size="34" font-weight="800" fill="{TEXT}">{money(price)}</text>
  <text x="{W - 40}" y="84" text-anchor="end" class="mono" font-size="12" fill="{chg_col}">{arrow} {abs(chg):.1f}% · 4 weeks</text>
  <g transform="translate({W - 128},96)">
    <circle cx="0" cy="0" r="4" fill="{RED}" class="blink"/>
    <text x="10" y="4" class="mono" font-size="10" font-weight="700" fill="{RED}" letter-spacing="2">LIVE</text>
    <text x="48" y="4" class="mono" font-size="10" fill="{MUTED}">{dt.date.today():%d %b %Y}</text>
  </g>
</g>

{"".join(g)}
{"".join(bars)}

<line x1="{cx0}" x2="{cx1}" y1="{py:.1f}" y2="{py:.1f}" stroke="{chg_col}" stroke-opacity=".6" class="dash"/>
<g transform="translate({last_x:.1f},{py:.1f})">
  <circle r="4" fill="{chg_col}" class="pulse"/><circle r="4" fill="{chg_col}"/>
</g>
<rect class="scan" x="{cx0 - 60}" y="{cy0}" width="60" height="{vy1 - cy0}" fill="url(#sc)"/>

<text x="{cx0}" y="400" class="mono" font-size="10" fill="{MUTED}">volume = contributions per week · last {WEEKS} weeks</text>
<text x="{cx1}" y="400" text-anchor="end" class="mono" font-size="10" fill="{MUTED}">updated daily by GitHub Actions</text>

<rect x="1" y="{H - 52}" width="{W - 2}" height="44" fill="#161b22"/>
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
    W, H = 840, 230
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
<rect width="{W}" height="{H}" rx="14" fill="#0d1117" stroke="#30363d"/>
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
