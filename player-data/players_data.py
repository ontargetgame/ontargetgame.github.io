#!/usr/bin/env python3
"""Player data for the football darts game.

One file, three jobs, Python 3.8+ standard library only:

  python3 players_data.py build    # one-off: every PL player since 1992 -> players.json
  python3 players_data.py refresh  # weekly: update current players from Fantasy PL
  python3 players_data.py check    # compare our top scorers with Wikipedia
  python3 players_data.py clubs    # add each player's PL clubs and years

players.json format:
  {
    "generated_at": "...", "season": "2026/27", "source": "...",
    "players": [
      {"id": "p2066", "name": "Alan Shearer", "goals": 260, "apps": 441,
       "position": "F", "current": false},
      ...
    ]
  }

`id` is the Opta player code ("p" + number), which both premierleague.com and
Fantasy PL use, so the two sources join cleanly. Players without an Opta code
fall back to "pl<premierleague.com id>".

`goals_before_season` is kept per player so the weekly refresh can add this
season's goals from Fantasy PL without re-pulling the whole history.
"""

import argparse
import datetime as dt
import gzip
import html
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

PULSE = "https://footballapi.pulselive.com/football"
FPL = "https://fantasy.premierleague.com/api/bootstrap-static/"
WIKI_API = "https://en.wikipedia.org/w/api.php"
PL_COMP_ID = 1  # Premier League in the Pulselive feed

# The Pulselive feed only answers requests that look like they come from the site.
PULSE_HEADERS = {
    "Origin": "https://www.premierleague.com",
    "Referer": "https://www.premierleague.com/",
    "Accept": "application/json",
}
UA = "Mozilla/5.0 (football-darts-game data script)"

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "players.json"


# ---------------------------------------------------------------- http

def get_json(url, headers=None, tries=4):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Encoding": "gzip",
                                               **(headers or {})})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return json.loads(body)
        except Exception as e:  # network blips, 5xx, rate limits
            if attempt == tries - 1:
                raise RuntimeError(f"GET {url} failed: {e}") from e
            retry_after = getattr(e, "headers", None) and e.headers.get("Retry-After")
            time.sleep(int(retry_after) + 1 if retry_after and retry_after.isdigit()
                       else 2 ** (attempt + 1))


def pulse(path, **params):
    url = f"{PULSE}/{path}?{urllib.parse.urlencode(params)}"
    return get_json(url, PULSE_HEADERS)


def ranked(stat, comp_season=None):
    """All pages of a ranked stat list (all-time if comp_season is None)."""
    rows, page = [], 0
    while True:
        params = dict(page=page, pageSize=100, comps=PL_COMP_ID,
                      compCodeForActivePlayer="EN_PR", altIds="true")
        if comp_season:
            params["compSeasons"] = comp_season
        data = pulse(f"stats/ranked/players/{stat}", **params)
        stats = data.get("stats", data)
        rows += stats.get("content", [])
        info = stats.get("pageInfo", {})
        page += 1
        print(f"  {stat}: page {page}/{info.get('numPages', '?')}", file=sys.stderr)
        if page >= info.get("numPages", 0):
            return rows
        time.sleep(0.3)  # be polite


# ---------------------------------------------------------------- helpers

def player_id(owner):
    opta = (owner.get("altIds") or {}).get("opta")
    if opta:
        return opta if str(opta).startswith("p") else f"p{opta}"
    return f"pl{int(owner['id'])}"


def display_name(owner):
    n = owner.get("name") or {}
    return n.get("display") or " ".join(x for x in (n.get("first"), n.get("last")) if x)


def fold(s):
    """Lower-case, accent-free, letters only: 'Agüero' -> 'aguero'."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", s.lower()).strip()


def current_season():
    data = pulse(f"competitions/{PL_COMP_ID}/compseasons", page=0, pageSize=100)
    latest = max(data["content"], key=lambda s: s["id"])
    return int(latest["id"]), latest["label"]


def fpl_players():
    """Fantasy PL squad list, keyed by our id."""
    data = get_json(FPL)
    out = {}
    for e in data["elements"]:
        if e.get("element_type") == 5:  # managers in "Assistant Manager" mode
            continue
        out[f"p{e['code']}"] = {
            "name": f"{e['first_name']} {e['second_name']}".strip(),
            "web_name": e["web_name"],
            "goals": int(e.get("goals_scored") or 0),
            "minutes": int(e.get("minutes") or 0),
            "position": {1: "G", 2: "D", 3: "M", 4: "F"}.get(e["element_type"]),
        }
    return out


def save(players, season, out, source):
    players.sort(key=lambda p: (-p["goals"], p["name"]))
    doc = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "season": season,
        "source": source,
        "count": len(players),
        "players": players,
    }
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    print(f"Wrote {len(players)} players to {out}", file=sys.stderr)


# ---------------------------------------------------------------- build

def build(out):
    season_id, season_label = current_season()
    print(f"Current season: {season_label} (id {season_id})", file=sys.stderr)

    players = {}
    # Appearances lists everyone who has played, including zero-goal players.
    for row in ranked("appearances"):
        o = row["owner"]
        pid = player_id(o)
        players[pid] = {
            "id": pid,
            "pl_id": int(o["id"]),
            "name": display_name(o),
            "goals": 0,
            "apps": int(row.get("value") or 0),
            "position": (o.get("info") or {}).get("position"),
            "current": False,
        }
    for row in ranked("goals"):
        o = row["owner"]
        pid = player_id(o)
        p = players.setdefault(pid, {"id": pid, "pl_id": int(o["id"]),
                                     "name": display_name(o), "apps": None,
                                     "position": (o.get("info") or {}).get("position"),
                                     "current": False})
        p["goals"] = int(row.get("value") or 0)

    this_season = {player_id(r["owner"]): int(r.get("value") or 0)
                   for r in ranked("goals", season_id)}
    for pid, p in players.items():
        p["goals_before_season"] = p["goals"] - this_season.get(pid, 0)

    try:
        fpl = fpl_players()
        for pid in fpl:
            if pid in players:
                players[pid]["current"] = True
        print(f"Marked {sum(p['current'] for p in players.values())} current players "
              f"from Fantasy PL ({len(fpl)} in FPL)", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Fantasy PL unavailable, 'current' left false: {e}", file=sys.stderr)

    save(list(players.values()), season_label, out,
         "premierleague.com (Pulselive) all-time; Fantasy PL for current squads")


# ---------------------------------------------------------------- refresh

def refresh(out):
    doc = json.loads(out.read_text())
    players = {p["id"]: p for p in doc["players"]}
    fpl = fpl_players()

    for p in players.values():
        p["current"] = False
    added = changed = 0
    for pid, f in fpl.items():
        p = players.get(pid)
        if p is None and not f["minutes"]:  # in a squad but yet to play in the PL
            continue
        if p is None:  # first PL season: new signing or promoted club
            p = players[pid] = {"id": pid, "pl_id": None, "name": f["name"],
                                "goals_before_season": 0, "goals": 0, "apps": None,
                                "position": f["position"], "current": True}
            added += 1
        new_goals = p.get("goals_before_season", p["goals"]) + f["goals"]
        changed += new_goals != p["goals"]
        p["goals"], p["current"] = new_goals, True

    print(f"Refresh: {len(fpl)} current players, {added} new, {changed} goal totals changed",
          file=sys.stderr)
    save(list(players.values()), doc.get("season"), out, doc.get("source", ""))


# ---------------------------------------------------------------- clubs

def clubs(out):
    """Add "clubs": [[club, from_year, to_year], ...] to every player, one entry per
    spell, from each season's squad appearance lists. Years are calendar years, so
    a 1996/97-2005/06 spell is [.., 1996, 2006]."""
    doc = json.loads(out.read_text())
    players = {p["id"]: p for p in doc["players"]}
    seasons = pulse(f"competitions/{PL_COMP_ID}/compseasons", page=0, pageSize=100)["content"]
    stints = {}  # pid -> {club: [season start years]}
    for s in sorted(seasons, key=lambda s: s["id"]):
        sid = int(s["id"])
        start = int(re.search(r"(\d{4})/", s["label"]).group(1))
        teams = pulse(f"compseasons/{sid}/teams")
        print(f"  {s['label']}: {len(teams)} clubs", file=sys.stderr)
        for t in teams:
            club = (t.get("club") or {}).get("shortName") or t.get("shortName") or t["name"]
            data = pulse("stats/ranked/players/appearances", page=0, pageSize=100,
                         comps=PL_COMP_ID, compSeasons=sid, teams=int(t["id"]), altIds="true")
            for row in data.get("stats", data).get("content", []):
                pid = player_id(row["owner"])
                stints.setdefault(pid, {}).setdefault(club, set()).add(start)
            time.sleep(0.2)

    for pid, p in players.items():
        spells = []
        for club, years in (stints.get(pid) or {}).items():
            years = sorted(years)
            first = prev = years[0]
            for y in years[1:] + [None]:
                if y is not None and y == prev + 1:
                    prev = y
                    continue
                spells.append([club, first, prev + 1])
                if y is not None:
                    first = prev = y
        p["clubs"] = sorted(spells, key=lambda c: (c[1], c[2]))
    missing = sum(1 for p in players.values() if not p["clubs"])
    print(f"Clubs added; {missing} players with no club found", file=sys.stderr)
    save(list(players.values()), doc.get("season"), out, doc.get("source", ""))


# ---------------------------------------------------------------- check

WIKI_HEADERS = {"User-Agent": "FootballDartsGame/0.1 (hobby game; player data check)"}


def wiki_top_scorers():
    """(name, goals) rows from Wikipedia's list of 100-goal PL scorers."""
    found = get_json(f"{WIKI_API}?" + urllib.parse.urlencode({
        "action": "query", "list": "search", "format": "json", "srlimit": 5,
        "srsearch": "List of Premier League players with 100 or more goals"}), WIKI_HEADERS)
    for hit in found["query"]["search"]:
        page = get_json(f"{WIKI_API}?" + urllib.parse.urlencode({
            "action": "parse", "page": hit["title"], "prop": "text",
            "format": "json", "formatversion": 2}), WIKI_HEADERS, tries=6)["parse"]["text"]
        # Columns: Rank, Player, Goals, Apps, ... Tied players share the Rank and
        # Goals cells (rowspan), so their rows start at Player and use the last Goals.
        rows, goals = [], None
        for tr in re.findall(r"<tr.*?</tr>", page, re.S):
            cells = [re.sub(r"\[\w+\]", "", html.unescape(re.sub(r"<[^>]+>", "", c))).strip()
                     for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)]
            if len(cells) >= 4 and cells[0].isdigit() and cells[2].isdigit():
                name, goals = cells[1], int(cells[2])
            elif len(cells) >= 2 and goals and cells[1].isdigit() and not cells[0].isdigit():
                name = cells[0]
            else:
                continue
            rows.append((name.replace("*", "").strip(), goals))
        if len(rows) >= 20:
            print(f"Wikipedia: {hit['title']} ({len(rows)} rows)", file=sys.stderr)
            return rows
    raise RuntimeError("Couldn't find a Wikipedia table of 100-goal scorers")


def check(out):
    ours = json.loads(out.read_text())["players"]
    by_name = {fold(p["name"]): p for p in ours}
    by_last = {}
    for p in ours:
        by_last.setdefault(fold(p["name"]).split(" ")[-1], []).append(p)

    problems = 0
    for name, goals in wiki_top_scorers():
        p = by_name.get(fold(name))
        if p is None:
            cands = [c for c in by_last.get(fold(name).split(" ")[-1], []) if c["goals"] >= 90]
            p = cands[0] if len(cands) == 1 else None
        if p is None:
            print(f"MISSING  {name} ({goals}) not found in our data")
            problems += 1
        elif abs(p["goals"] - goals) > 1:  # Wikipedia can lag a game behind
            print(f"DIFF     {name}: Wikipedia {goals}, ours {p['goals']}")
            problems += 1
        else:
            print(f"ok       {name}: {p['goals']}")
    print(f"\n{problems} problem(s)")
    return problems


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("job", choices=["build", "refresh", "check", "clubs"])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args()
    if a.job == "build":
        build(a.out)
    elif a.job == "refresh":
        refresh(a.out)
    elif a.job == "clubs":
        clubs(a.out)
    else:
        sys.exit(1 if check(a.out) else 0)


if __name__ == "__main__":
    main()
