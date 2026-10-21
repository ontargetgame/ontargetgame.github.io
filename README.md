# On Target

Pick 3 to 5 Premier League players whose career PL goals add up as close to the target as you can, without going over. Play solo or head-to-head on one phone.

Play: https://ontargetgame.github.io/

## How it's built

A static site with no server. `index.html` + `players.js` are the whole game.

- `app.html` is the page itself (edit this).
- `python3 build.py` regenerates `players.js` from `player-data/players.json` and wraps `app.html` into `index.html`.
- `player-data/players_data.py` builds and refreshes the player list (see `player-data/README.md`).

Weekly update: `python3 player-data/players_data.py refresh`, then `python3 build.py`, then commit and push.
