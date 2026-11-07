# On Target

Pick 3 to 5 Premier League players whose career PL goals add up as close to the target as you can, without going over. Play solo or head-to-head on one phone.

Higher or lower: say whether the next player has more or fewer career PL appearances than the one shown, and build a streak.

Play: https://ontargetgame.github.io/

## How it's built

A static site. `index.html` + `players.js` are the whole game. Optional accounts (email-link sign-in, saved stats) use a free Supabase project: `vendor/supabase-2.110.0.js` is the Supabase client, `supabase/*.sql` are the database scripts (run them in Supabase's SQL Editor), and `.github/workflows/keepalive.yml` pings the database twice a week so the free project doesn't pause.

- `app.html` is the page itself (edit this).
- `python3 build.py` regenerates `players.js` from `player-data/players.json` and wraps `app.html` into `index.html`.
- `player-data/players_data.py` builds and refreshes the player list (see `player-data/README.md`).

Weekly update: `python3 player-data/players_data.py refresh`, then `python3 build.py`, then commit and push.
