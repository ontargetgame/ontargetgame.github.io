#!/usr/bin/env python3
"""Builds the game from player-data/players.json.

  python3 build.py

Writes players.js (the compact list the page reads) and index.html (app.html
wrapped as a full page). Upload index.html + players.js to any static host.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "player-data" if (HERE / "player-data").exists() else HERE.parent / "player-data"
doc = json.loads((DATA / "players.json").read_text())


def clubs_and_years(p):
    spells = p.get("clubs") or []
    if not spells:
        return "", ""
    seasons = {}
    for club, a, b in spells:
        seasons[club] = seasons.get(club, 0) + (b - a)
    first = {}
    for club, a, _ in spells:
        first.setdefault(club, a)
    main = sorted(seasons, key=lambda c: -seasons[c])[:3]
    main.sort(key=lambda c: first[c])
    more = len(seasons) - len(main)
    label = ", ".join(main) + (f" +{more}" if more > 0 else "")
    lo, hi = min(s[1] for s in spells), max(s[2] for s in spells)
    years = f"{lo}–{hi}" if not p.get("current") else f"{lo}–now"
    return label, years


rows = []
for p in doc["players"]:
    c, y = clubs_and_years(p)
    rows.append([p["name"], p["goals"], p.get("apps") or 0, c, y, p.get("position") or ""])
data = {"asof": doc["generated_at"][:10], "players": rows}
(HERE / "players.js").write_text("window.FD_DATA=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n")

app = (HERE / "app.html").read_text()
(HERE / "index.html").write_text(
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    "<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}"
    "body{margin:0}[hidden]{display:none!important}</style>\n</head>\n<body>\n" + app + "\n</body>\n</html>\n")
print(f"players.js: {len(rows)} players; index.html written")
