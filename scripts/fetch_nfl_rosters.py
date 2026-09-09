#!/usr/bin/env python3
"""
Pulls the full current NFL active roster (skill positions) from ESPN's
roster endpoint and writes data/nfl-players.json.

*** WHY THIS REPLACES THE PREVIOUS nflverse-BASED VERSION ***
nflverse's roster file and player-stats file didn't always agree on name
spelling for the same person (confirmed live: "DJ Moore" in one, "D.J.
Moore" in the other, same actual person), which created duplicate,
disconnected entries. Switching both this script and fetch_players_nfl.py
to ESPN's API means they now share the SAME athlete ID scheme (ESPN's own
numeric "id"), which fixes that whole class of bug rather than patching
around it.

*** HONESTY NOTE ***
The team ID -> abbreviation mapping below was directly verified live
against ESPN's /teams endpoint (Sept 2026) for every team except PIT,
SF, SEA, TB, TEN, WAS, which use ESPN's long-standing, widely-documented
ID scheme but weren't in the single API response fetched while writing
this (it was long enough to get cut off around 26 teams). If any one
team's roster comes back with 0 players, that team's ID is the first
thing to double check.

Source: https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{TEAM_ID}/roster

Run: python3 scripts/fetch_nfl_rosters.py
Writes: data/nfl-players.json
"""
import json
import sys
import urllib.request

EXISTING_PATH = "data/nfl-players.json"
SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}
YEAR = 2026

TEAM_IDS = {
    "ARI": 22, "ATL": 1, "BAL": 33, "BUF": 2, "CAR": 29, "CHI": 3, "CIN": 4,
    "CLE": 5, "DAL": 6, "DEN": 7, "DET": 8, "GB": 9, "HOU": 34, "IND": 11,
    "JAX": 30, "KC": 12, "LV": 13, "LAC": 24, "LAR": 14, "MIA": 15, "MIN": 16,
    "NE": 17, "NO": 18, "NYG": 19, "NYJ": 20, "PHI": 21, "PIT": 23, "SF": 25,
    "SEA": 26, "TB": 27, "TEN": 10, "WAS": 28,
}
TEAM_NAMES = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills", "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs", "LV": "Las Vegas Raiders", "LAC": "Los Angeles Chargers",
    "LAR": "Los Angeles Rams", "MIA": "Miami Dolphins", "MIN": "Minnesota Vikings",
    "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers",
    "SF": "San Francisco 49ers", "SEA": "Seattle Seahawks", "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}


def api_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "matchup-room-fetcher"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    try:
        with open(EXISTING_PATH) as f:
            players = json.load(f)
    except FileNotFoundError:
        players = {}

    # Existing entries indexed by ESPN athlete id, so a person keeps the
    # same dict entry (and any games already attached to it) even if
    # their display name ever renders slightly differently between runs.
    existing_by_id = {v.get("_id"): k for k, v in players.items() if v.get("_id")}

    updated = 0
    team_errors = 0
    for abbr, team_id in TEAM_IDS.items():
        url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/roster"
        try:
            data = api_get(url)
        except Exception as e:
            print(f"Could not fetch {abbr} (team id {team_id}) roster ({e}); skipping this team.", file=sys.stderr)
            team_errors += 1
            continue

        groups = data.get("athletes", [])
        if not groups:
            print(f"WARNING: {abbr} (team id {team_id}) roster came back empty -- double check this team's ID.", file=sys.stderr)

        for group in groups:
            for row in group.get("items", []):
                pos = (row.get("position") or {}).get("abbreviation")
                if pos not in SKILL_POSITIONS:
                    continue
                if (row.get("status") or {}).get("type") != "active":
                    continue
                espn_id = row.get("id")
                name = row.get("fullName") or row.get("displayName")
                if not espn_id or not name:
                    continue

                key = existing_by_id.get(espn_id, name)
                existing = players.get(key, {})
                players[key] = {
                    "pos": pos,
                    "team": TEAM_NAMES[abbr],
                    "league": "NFL",
                    "games": existing.get("games", []),  # preserved by fetch_players_nfl.py, not touched here
                    "_id": espn_id,
                    "teamYear": YEAR,
                }
                updated += 1

    with open(EXISTING_PATH, "w") as f:
        json.dump(players, f, indent=2)
    print(f"Wrote/updated {updated} NFL players across {len(TEAM_IDS) - team_errors}/{len(TEAM_IDS)} teams to {EXISTING_PATH}")


if __name__ == "__main__":
    main()
