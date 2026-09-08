# Matchup Room

Football stats, matchup projections, player prop hit rates, and a parlay
calculator for the NFL and Power 5 college football.

This repo is set up to auto-refresh its own data weekly, for free, using
GitHub Pages + GitHub Actions. Here's how to turn it on.

## 1. Get this repo on GitHub

- Create a free GitHub account if you don't have one.
- Create a new repository (public — GitHub Actions' free scheduled runs
  require a public repo).
- Upload everything in this folder to it (or `git init` / `git push` if
  you're comfortable with git).

## 2. Turn on GitHub Pages (this gives you your shareable link)

- In the repo, go to **Settings → Pages**.
- Under "Build and deployment", set Source to **Deploy from a branch**,
  branch `main`, folder `/ (root)`.
- Save. After a minute or two you'll get a URL like
  `https://yourname.github.io/repo-name/` — that's your live, shareable site.

## 3. Get free API keys (only needed for auto-updating stats/odds)

The site works immediately with the data already in `data/` — these keys
are only needed so the **weekly auto-update** can pull fresh numbers.

- **College football stats**: sign up free at
  https://collegefootballdata.com — copy your API key.
- **Odds**: sign up free at https://the-odds-api.com — copy your API key.
  (No key needed for NFL stats — that script pulls from nflverse, which is
  open data.)

## 4. Add the keys as repo secrets

In the repo: **Settings → Secrets and variables → Actions → New repository
secret**. Add two:

| Name | Value |
|---|---|
| `CFBD_API_KEY` | your CollegeFootballData key |
| `ODDS_API_KEY` | your Odds API key |

## 5. Turn on the scheduled update

It's already set up in `.github/workflows/update-data.yml` to run every
Tuesday at 9am UTC. To also run it right now (don't wait for Tuesday):

- Go to the **Actions** tab → **Update stats and odds** → **Run workflow**.

That's it. Every week, seven scripts run automatically:

- `scripts/fetch_nfl.py` — pulls fresh NFL team stats from nflverse (free, no key)
- `scripts/fetch_nfl_schedule.py` — pulls the current week's NFL schedule + real spread/total/moneyline lines from nflverse (free, no key) — auto-advances week to week on its own
- `scripts/fetch_players_nfl.py` — pulls every NFL QB/RB/WR/TE's per-game stat lines from nflverse (free, no key)
- `scripts/fetch_cfb.py` — pulls fresh Power 5 college team stats from CollegeFootballData
- `scripts/fetch_cfb_schedule.py` — pulls the current week's AP Top 25 rankings and ranked-vs-ranked matchups from CollegeFootballData — also auto-advances week to week
- `scripts/fetch_players_cfb.py` — pulls Power 5 college players' per-game stat lines from CollegeFootballData
- `scripts/fetch_odds.py` — pulls fresh odds from The Odds API

They write their results into `data/*.json`, and the workflow commits those
changes automatically. Your page (`index.html`) fetches those JSON files
on load, falling back to whatever was last saved if a fetch ever fails.

## What's NOT automated yet

- **CFB turnover margin** — CollegeFootballData's stats endpoints don't
  surface this as a simple per-team-per-game number the way we need; left
  as whatever was already there rather than guessed.
- **Live odds/stats that refresh themselves without you asking** — this is
  a static page with no server, so "automated" here means "runs on GitHub's
  free weekly schedule," not "updates in real time as you watch." Trigger
  the Action manually from the Actions tab any time you want a fresher pull.

## Important: test the CFBD-based scripts locally before trusting the automation

`scripts/fetch_nfl.py`, `scripts/fetch_nfl_schedule.py`, and
`scripts/fetch_players_nfl.py` were all tested against real, live nflverse
data while being built — they work. `fetch_nfl_schedule.py` in particular
was confirmed to correctly detect "Week 1" (since the 2026 season hasn't
played yet) and produced the exact same 16 matchups already in the site,
plus real spread/total/moneyline lines for all of them.

`scripts/fetch_cfb.py`, `scripts/fetch_cfb_schedule.py`, and
`scripts/fetch_players_cfb.py` could **not** be tested the same way — the
sandbox that built this doesn't have network access to
collegefootballdata.com. `fetch_cfb.py` has already been confirmed working
against your live API key (see below). `fetch_cfb_schedule.py` and
`fetch_players_cfb.py` have not been run against real data at all yet.
Before trusting either:

```bash
CFBD_API_KEY=xxxx python3 scripts/fetch_cfb_schedule.py
cat data/cfb-rankings.json
cat data/cfb-schedule.json
CFBD_API_KEY=xxxx python3 scripts/fetch_players_cfb.py
cat data/cfb-players.json | head -50
```

If either comes back empty or with a warning printed to stderr about the
response shape, the API's field names have likely changed or the nesting
is different than assumed — the warning prints a sample raw row from CFBD
so you (or I, if you paste it back) can see what actually came back and
fix the parsing.

**Status so far, for reference**: `fetch_cfb.py` needed two real fixes
after being deployed — stripping whitespace from the API key secret, and
falling back to per-week requests since `/games/teams` rejects a bare
`year`. Both fixes are applied to `fetch_cfb_schedule.py` and
`fetch_players_cfb.py` too, since they hit the same kind of endpoints, but
that's a reasonable guess based on the pattern, not a confirmed fix for
those specific endpoints.

## Local testing

You can run any fetch script locally before trusting the automation:

```bash
pip install -r requirements.txt
CFBD_API_KEY=xxxx python3 scripts/fetch_cfb.py
CFBD_API_KEY=xxxx python3 scripts/fetch_cfb_schedule.py
CFBD_API_KEY=xxxx python3 scripts/fetch_players_cfb.py
ODDS_API_KEY=xxxx python3 scripts/fetch_odds.py
python3 scripts/fetch_nfl.py            # no key needed
python3 scripts/fetch_nfl_schedule.py   # no key needed
python3 scripts/fetch_players_nfl.py    # no key needed
```

Then open `index.html` locally (or via a simple `python3 -m http.server`)
to see the updated data reflected.

## A note on accuracy

These fetch scripts were written against each API's documented shape as of
when this was built, but external APIs change their fields and endpoints
over time. If a script starts silently doing nothing useful, check:

- nflverse: https://github.com/nflverse/nflverse-data/releases
- CollegeFootballData docs: https://api.collegefootballdata.com/api-docs
- The Odds API docs: https://the-odds-api.com/liveapi/guides/v4/

Each script fails safely (leaves the existing JSON file alone) rather than
overwriting good data with errors or zeros.

## Site structure

NFL and college football are kept completely separate in the UI — top-level
tabs for **NFL**, **CFB**, and **Parlay Calc**, each NFL/CFB tab has its own
This Week / Teams / Matchup / Players / Trends sub-tabs (CFB also has a
Rankings sub-tab). Nothing crosses between leagues except the parlay slip,
which can hold legs from either.

