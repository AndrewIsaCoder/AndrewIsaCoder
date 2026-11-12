"""'Watchlist' card: the most active repositories shown like stock holdings."""
from __future__ import annotations

import datetime as dt
from html import escape

from generate import FONT, GREEN, GRID, LANG_COLORS, MONO, MUTED, RED, TEXT


def symbol(name: str) -> str:
    parts = [w for w in name.replace("_", "-").replace(".", "-").split("-") if w]
    sym = "".join(w[0] for w in parts) if len(parts) > 1 else name
    if len(sym) < 3:
        sym = (parts[0] + "".join(parts[1:])) if parts else name
    return "".join(ch for ch in sym.upper() if ch.isalnum())[:4]


def ago(iso: str) -> str:
    d = (dt.date.today() - dt.date.fromisoformat(iso)).days
    if d <= 0:
        return "today"
    if d < 30:
        return f"{d}d ago"
    if d < 365:
        return f"{d // 30}mo ago"
    return f"{d // 365}y ago"


def _rows(p: dict, limit: int) -> list[dict]:
    today = dt.date.today()
    rows = []
    for r in p["repos"]:
        dates = [dt.date.fromisoformat(c) for c in r.get("commits", [])]
        age = [(today - d).days for d in dates]
        weekly = [sum(1 for a in age if 7 * (11 - w) <= a < 7 * (12 - w)) for w in range(12)]
        rows.append({**r, "weekly": weekly,
                     "c30": sum(1 for a in age if a < 30),
                     "p30": sum(1 for a in age if 30 <= a < 60)})
    rows.sort(key=lambda r: (sum(r["weekly"]), r["stars"], r.get("pushed", "")), reverse=True)
    return rows[:limit]


def projects_svg(p: dict) -> str:
    rows = _rows(p, 6)
    W, RH, top = 860, 56, 104
    H = top + len(rows) * RH + 44
    X = {"sym": 28, "lang": 340, "trend": 458, "px": 652, "chg": 724, "star": 752, "upd": 832}

    head = "".join(
        f'<text x="{x}" y="{top - 12}" class="hd" text-anchor="{a}">{t}</text>'
        for t, x, a in [("SYMBOL / PROJECT", X["sym"], "start"), ("SECTOR", X["lang"], "start"),
                        ("12W ACTIVITY", X["trend"], "start"), ("30D", X["px"], "end"),
                        ("CHG", X["chg"] - 24, "middle"), ("STARS", X["star"], "end"),
                        ("UPDATED", X["upd"], "end")])

    body = []
    for i, r in enumerate(rows):
        y0 = top + i * RH
        mid = y0 + RH / 2
        lc = LANG_COLORS.get(r["lang"] or "", MUTED)
        up = r["c30"] >= r["p30"]
        col = GREEN if up else RED
        if r["p30"]:
            sign = "+" if up else "−"
            chg = f'{sign}{abs(r["c30"] - r["p30"]) / r["p30"] * 100:.0f}%'
        elif r["c30"]:
            chg = "NEW"
        else:
            chg, col = "0%", MUTED

        wk = r["weekly"]
        mx = max(max(wk), 1)
        sx0, sw, sh = X["trend"], 150, 24
        pts = [(sx0 + k * sw / 11, mid + sh / 2 - v / mx * sh) for k, v in enumerate(wk)]
        line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        area = f"{sx0},{mid + sh / 2:.1f} {line} {sx0 + sw},{mid + sh / 2:.1f}"

        name = r["name"] if len(r["name"]) <= 28 else r["name"][:27] + "…"
        desc = (r.get("desc") or "No description").strip()
        desc = desc if len(desc) <= 42 else desc[:41] + "…"
        d = 0.2 + i * 0.12
        upd = ago(r["pushed"]) if r.get("pushed") else "—"
        body.append(
            f'<g class="row" style="animation-delay:{d:.2f}s">'
            f'<line x1="1" x2="{W - 1}" y1="{y0 + RH}" y2="{y0 + RH}" stroke="{GRID}"/>'
            f'<rect x="{X["sym"]}" y="{mid - 15}" width="56" height="30" rx="6" fill="{lc}" '
            f'fill-opacity=".16" stroke="{lc}" stroke-opacity=".7"/>'
            f'<text x="{X["sym"] + 28}" y="{mid + 4.5}" class="sym" text-anchor="middle" fill="{lc}">'
            f'{escape(symbol(r["name"]))}</text>'
            f'<text x="{X["sym"] + 70}" y="{mid - 3}" class="nm">{escape(name)}</text>'
            f'<text x="{X["sym"] + 70}" y="{mid + 14}" class="ds">{escape(desc)}</text>'
            f'<circle cx="{X["lang"] + 5}" cy="{mid}" r="5" fill="{lc}"/>'
            f'<text x="{X["lang"] + 16}" y="{mid + 4}" class="ds" fill="#c9d1d9">'
            f'{escape((r["lang"] or "—").replace(" Notebook", "")[:13])}</text>'
            f'<polygon points="{area}" fill="{col}" fill-opacity=".13" class="fade" '
            f'style="animation-delay:{d + .7:.2f}s"/>'
            f'<polyline points="{line}" pathLength="1" fill="none" stroke="{col}" stroke-width="1.6" '
            f'stroke-linejoin="round" class="spark" style="animation-delay:{d + .2:.2f}s"/>'
            f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="2.6" fill="{col}" class="pulse" '
            f'style="animation-delay:{i * .3:.1f}s"/>'
            f'<text x="{X["px"]}" y="{mid + 5}" class="val" text-anchor="end">{r["c30"]}</text>'
            f'<rect x="{X["chg"] - 52}" y="{mid - 11}" width="56" height="22" rx="4" fill="{col}" fill-opacity=".15"/>'
            f'<text x="{X["chg"] - 24}" y="{mid + 4.5}" class="val sm" text-anchor="middle" fill="{col}">{chg}</text>'
            f'<text x="{X["star"]}" y="{mid + 5}" class="val" text-anchor="end">{r["stars"]}</text>'
            f'<text x="{X["upd"]}" y="{mid + 4}" class="ds" text-anchor="end">{upd}</text>'
            f'</g>')

    n = max(len(rows), 1)
    cycle, share = n * 1.6, 100 / n
    scan = "".join(
        f'<rect class="hl" style="animation-delay:{2 + i * 1.6:.1f}s" x="1" y="{top + i * RH}" '
        f'width="{W - 2}" height="{RH}" fill="#2f81f7"/>' for i in range(len(rows)))
    total30 = sum(r["c30"] for r in rows)

    css = f"""
.hd{{font-family:{MONO};font-size:9.5px;fill:{MUTED};letter-spacing:1.2px}}
.sym{{font-family:{MONO};font-size:12px;font-weight:800;letter-spacing:.5px}}
.nm{{font-size:14px;font-weight:700;fill:{TEXT}}}
.ds{{font-size:11.5px;fill:{MUTED}}}
.val{{font-family:{MONO};font-size:14px;font-weight:700;fill:{TEXT}}}
.sm{{font-size:11.5px}}
.row{{opacity:0;animation:in .6s ease forwards}}
@keyframes in{{from{{opacity:0;transform:translateX(-12px)}}to{{opacity:1;transform:none}}}}
.spark{{stroke-dasharray:1;stroke-dashoffset:1;animation:draw 1.2s ease-out forwards}}
@keyframes draw{{to{{stroke-dashoffset:0}}}}
.fade{{opacity:0;animation:fade .8s ease forwards}}
@keyframes fade{{to{{opacity:1}}}}
.pulse{{transform-box:fill-box;transform-origin:center;animation:ping 1.8s ease-out infinite}}
@keyframes ping{{0%{{transform:scale(1);opacity:1}}70%{{transform:scale(2.6);opacity:.25}}100%{{transform:scale(1);opacity:1}}}}
.hl{{opacity:0;animation:hl {cycle:.1f}s ease-in-out infinite}}
@keyframes hl{{0%{{opacity:0}}{share * .3:.2f}%{{opacity:.09}}{share * .7:.2f}%{{opacity:.09}}{share:.2f}%,100%{{opacity:0}}}}
.blink{{animation:blink 1.2s steps(2,start) infinite}}
@keyframes blink{{to{{visibility:hidden}}}}
"""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'font-family="{FONT}"><style>{css}</style>'
        f'<rect width="{W}" height="{H}" rx="12" fill="#0d1117" stroke="#30363d"/>'
        f'<text x="28" y="40" font-family="{MONO}" font-size="11" font-weight="700" fill="{GREEN}" '
        f'letter-spacing="2"><tspan class="blink">●</tspan> WATCHLIST · TOP HOLDINGS</text>'
        f'<text x="28" y="68" font-size="22" font-weight="800" fill="{TEXT}">Projects</text>'
        f'<text x="{W - 28}" y="40" text-anchor="end" font-family="{MONO}" font-size="10" fill="{MUTED}">'
        f'ranked by commits · last 12 weeks</text>'
        f'<text x="{W - 28}" y="66" text-anchor="end" font-family="{MONO}" font-size="14" font-weight="700" '
        f'fill="{TEXT}">{total30} <tspan fill="{MUTED}" font-weight="400" font-size="12">commits / 30d</tspan></text>'
        f'<line x1="1" x2="{W - 1}" y1="{top}" y2="{top}" stroke="#30363d"/>'
        f'{head}{scan}{"".join(body)}'
        f'<text x="28" y="{H - 16}" font-family="{MONO}" font-size="9.5" fill="#484f58">30D = commits on the '
        f'default branch in the last 30 days · CHG vs the 30 days before · refreshed every 6h</text>'
        f'</svg>')
