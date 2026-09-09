#!/usr/bin/env python3
"""
Pulls the full current NFL active roster (skill positions) from nflverse's
roster file and writes data/nfl-players.json -- this is what fixes team
assignment BEFORE the season starts, since nflverse's game-by-game player
stats (fetch_players_nfl.py) don't exist yet for 2026.

*** REAL BUG THIS VERSION FIXES ***
The original version keyed players purely by display name. nflverse's own
files don't agree on name formatting for the same person -- e.g. this
roster file spells a player "DJ Moore" while the historical stats file
spells the same person (same gsis_id, verified) "D.J. Moore". That
created two disconnected dictionary entries: one with his current team
and no games, one with his old team and real games. Now every entry also
carries "_id" (the gsis_id) and "teamYear" (which year's roster last
confirmed this team). fetch_players_nfl.py matches by "_id" first, name
only as a fallback for players who've never appeared on any roster this
script has processed -- this is what actually fixes the duplicate-entry
problem, not just papering over it.

"teamYear" also solves a second real bug: a player who falls off every
team's active roster (retired, unsigned, etc. -- confirmed live: this
happened to Amari Cooper, who isn't on any 2026 roster at all) previously
kept showing his last known team forever, with no way to tell it was
stale. Now the team field alone can't be trusted as "confirmed current"
unless teamYear matches this run's YEAR -- the UI uses this to show a
"not on a 2026 active roster" caveat instead of silently asserting a
team that's no longer accurate.

Verified live while writing this: roster_2026.csv correctly shows Mack
Hollins on NE (Patriots), not BUF -- confirming this file reflects
current 2026 rosters, unlike box-score data which won't exist until real
games are played.

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
    for row in rows:
        if row.get("status") != "ACT":
            continue
        if row.get("position") not in SKILL_POSITIONS:
            continue
        name = row.get("full_name")
        gsis_id = row.get("gsis_id")
        if not name:
            continue

        # If we already have an entry for this exact person (by ID) under
        # a different name spelling, keep using that entry's key so games
        # already attached to it don't get orphaned.
        key = existing_by_id.get(gsis_id, name) if gsis_id else name
        existing = players.get(key, {})

        team_abbr = row.get("team")
        players[key] = {
            "pos": row.get("position"),
            "team": TEAM_NAME_MAP.get(team_abbr, team_abbr),
            "league": "NFL",
            "games": existing.get("games", []),  # preserve any games already attached to this person
            "_id": gsis_id,
            "teamYear": YEAR,
        }
        updated += 1

    with open(EXISTING_PATH, "w") as f:
        json.dump(players, f, indent=2)
    print(f"Wrote/updated {updated} NFL players (current active roster) to {EXISTING_PATH}")


if __name__ == "__main__":
    main()
