#!/usr/bin/env python3
"""
Pulls the full current NFL active roster (skill positions) from nflverse's
roster file and writes data/nfl-players.json -- this is what fixes team
assignment BEFORE the season starts, since nflverse's game-by-game player
stats (fetch_players_nfl.py) don't exist yet for 2026.

*** BACK TO nflverse -- ESPN DOESN'T WORK FROM GITHUB ACTIONS ***
A version of this script briefly used ESPN's API instead (ESPN's data is
more current -- see fetch_players_nfl.py's docstring). It was verified
working when fetched directly, but failed with HTTP 403 Forbidden for
every single team when actually run from GitHub Actions. That's
consistent with Cloudflare-style bot protection blocking cloud/datacenter
IP ranges specifically -- something no amount of header tweaking fixes
from a headless HTTP client, and not something that could be verified
without actually deploying and watching it fail live (which is exactly
what happened). Reverted to nflverse, which has a real track record of
working reliably from this exact Actions environment.

*** REAL BUG THIS VERSION STILL FIXES ***
nflverse's own roster file and its historical stats file don't always
agree on name formatting for the same person -- e.g. the roster file
spells a player "DJ Moore" while the historical stats file spells the
same person (same gsis_id, verified) "D.J. Moore". That created two
disconnected dictionary entries: one with his current team and no games,
one with his old team and real games. Every entry here also carries
"_id" (the gsis_id) and "teamYear" (which year's roster last confirmed
this team) so fetch_players_nfl.py can match by ID first, name only as a
fallback -- this is what actually fixes the duplicate-entry problem.

"teamYear" also solves a second real bug: a player who falls off every
team's active roster (retired, unsigned, etc. -- confirmed live: this
happened to Amari Cooper) previously kept showing his last known team
forever, with no way to tell it was stale. Now the team field alone can't
be trusted as "confirmed current" unless teamYear matches this run's
YEAR -- the UI uses this to show a "not on a 2026 active roster" caveat.

*** NOW ACTUALLY PRUNES STALE PLAYERS, NOT JUST FLAGS THEM ***
The teamYear flag alone wasn't enough -- confirmed live, 263 of 767
stored NFL players (34%) had gone stale at once, just sitting there
indefinitely with nothing ever removing them. This run now deletes any
player entry whose gsis_id isn't in the CURRENT active roster this run
pulled -- covering both real roster departures (retired, released,
unsigned) and orphaned old-format entries from before the gsis_id system
existed (a spelling-mismatched duplicate with no _id at all could never
be confirmed current, so it's pruned too). fetch_players_nfl.py runs
right after this and only processes a gsis_id that already has an entry
here, so a pruned player won't get silently re-added by that next step.

Verified live while writing this originally: roster_2026.csv correctly
shows Mack Hollins on NE (Patriots), not BUF -- confirming this file
reflects current 2026 rosters, unlike box-score data which won't exist
until real games are played.

Source (verified): https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_{YEAR}.csv

Run: python3 scripts/fetch_nfl_rosters.py
Writes: data/nfl-players.json
"""
import csv
import io
import json
import sys
import urllib.request

YEAR = 2026
ROSTER_URL = f"https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_{YEAR}.csv"
EXISTING_PATH = "data/nfl-players.json"
SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}

TEAM_NAME_MAP = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills", "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs", "LAC": "Los Angeles Chargers", "LA": "Los Angeles Rams",
    "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins", "MIN": "Minnesota Vikings",
    "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers",
    "SEA": "Seattle Seahawks", "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}


def fetch_csv(url):
    req = urllib.request.Request(url, headers={"User-Agent": "matchup-room-fetcher"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(raw)))


def main():
    try:
        with open(EXISTING_PATH) as f:
            players = json.load(f)
    except FileNotFoundError:
        players = {}

    try:
        rows = fetch_csv(ROSTER_URL)
    except Exception as e:
        print(f"Could not fetch roster_{YEAR}.csv ({e}); leaving existing file untouched.", file=sys.stderr)
        return

    # Existing entries indexed by gsis_id, so a name-spelling difference
    # from a prior run (or from fetch_players_nfl.py) doesn't cause a
    # second, disconnected entry to get created for the same person.
    existing_by_id = {v.get("_id"): k for k, v in players.items() if v.get("_id")}

    updated = 0
    current_ids = set()
    for row in rows:
        if row.get("status") != "ACT":
            continue
        if row.get("position") not in SKILL_POSITIONS:
            continue
        name = row.get("full_name")
        gsis_id = row.get("gsis_id")
        if not name:
            continue
        if gsis_id:
            current_ids.add(gsis_id)

        key = existing_by_id.get(gsis_id, name) if gsis_id else name
        existing = players.get(key, {})

        team_abbr = row.get("team")
        players[key] = {
            "pos": row.get("position"),
            "team": TEAM_NAME_MAP.get(team_abbr, team_abbr),
            "league": "NFL",
            "games": existing.get("games", []),
            "_id": gsis_id,
            "teamYear": YEAR,
        }
        updated += 1

    # Prune anyone NOT on this run's confirmed active roster -- retired,
    # released, or otherwise off every team's roster. Confirmed live: this
    # is a real, sizable problem, not a hypothetical one -- 263 of 767
    # stored players (34%) were stale at once (Amari Cooper still attached
    # to a team after retiring; a name-spelling mismatch from long before
    # the gsis_id fix existed leaving a permanently stale "D.J. Moore"
    # duplicate that a fresh, correctly-tagged "DJ Moore" entry never
    # overwrote, since they're different dict keys). Without this, a
    # player who falls off a roster just sits here forever -- teamYear
    # correctly flagged them as stale, but nothing ever acted on it.
    # fetch_players_nfl.py is safe to run after this: it only processes a
    # gsis_id that ALREADY has an entry here (skips anyone it can't match),
    # so a pruned player won't get silently re-added by that next step.
    before_prune = len(players)
    players = {k: v for k, v in players.items() if v.get("_id") in current_ids}
    pruned = before_prune - len(players)

    with open(EXISTING_PATH, "w") as f:
        json.dump(players, f, indent=2)
    print(f"Wrote/updated {updated} NFL players (current active roster) to {EXISTING_PATH}; pruned {pruned} no-longer-active entries")


if __name__ == "__main__":
    main()
