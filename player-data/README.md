# Player data

`players_data.py` makes `players.json`, the list the game reads. Needs Python 3.8+, nothing to install.

| Command | When | What it does |
|---|---|---|
| `python3 players_data.py build` | Once (or to start fresh) | Pulls every Premier League player since 1992 from premierleague.com's feed: name, id, career PL goals, appearances, position. Marks who is in a current squad using Fantasy PL. About 2 minutes. |
| `python3 players_data.py refresh` | Weekly | Reads Fantasy PL, updates this season's goals for current players, adds new arrivals, and clears `current` for anyone who left. |
| `python3 players_data.py clubs` | After a build | Adds each player's PL clubs and years (`"clubs": [["Newcastle", 1996, 2006], ...]`, one entry per spell). About 8 minutes. |
| `python3 players_data.py check` | After a build | Compares our 100-goal scorers with Wikipedia's list and prints any that are missing or differ by more than 1. |

Each player looks like:

```json
{"id": "p1", "pl_id": 89, "name": "Alan Shearer", "goals": 260, "apps": 441, "position": "F", "current": false, "goals_before_season": 260}
```

`id` is the Opta code that premierleague.com and Fantasy PL share. Goals are Premier League league goals only (no cups, no own goals), per the rules doc.

Last build: 2026-10-20, 5,218 players, `check` matched all 35 of Wikipedia's 100-goal scorers. 29 names are shared by two different players (e.g. Mark Hughes, Alan Smith), clubs and years (from `clubs`) tell them apart.
