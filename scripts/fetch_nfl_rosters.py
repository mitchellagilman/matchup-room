#!/usr/bin/env python3
"""
Pulls the full current NFL active roster (skill positions) from nflverse's
roster file and writes data/nfl-players.json -- this is what fixes team
assignment BEFORE the season starts, since nflverse's game-by-game player
stats (fetch_players_nfl.py) don't exist yet for 2026.

Verified live while writing this: roster_2026.csv correctly shows Mack
Hollins on NE (Patriots), not BUF -- confirming this file reflects
current 2026 rosters, unlike box-score data which won't exist until real
games are played.

Source (verified): https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_{YEAR}.csv

This only sets team/position (with an empty game log) for players who
don't already have real logged games. Once fetch_players_nfl.py starts
finding actual 2026 box scores, that script's team assignment (pulled
from the game itself) is more authoritative and this script won't
clobber it -- it skips anyone who already has a non-empty game log.

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

    updated = 0
    for row in rows:
        if row.get("status") != "ACT":
            continue
        if row.get("position") not in SKILL_POSITIONS:
            continue
        name = row.get("full_name")
        if not name:
            continue
        existing = players.get(name)
        if existing and existing.get("games"):
            continue  # already has real logged games -- don't overwrite with a roster snapshot
        team_abbr = row.get("team")
        players[name] = {
            "pos": row.get("position"),
            "team": TEAM_NAME_MAP.get(team_abbr, team_abbr),
            "league": "NFL",
            "games": [],
        }
        updated += 1

    with open(EXISTING_PATH, "w") as f:
        json.dump(players, f, indent=2)
    print(f"Wrote/updated {updated} NFL players (current active roster) to {EXISTING_PATH}")


if __name__ == "__main__":
    main()
