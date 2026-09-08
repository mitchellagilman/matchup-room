#!/usr/bin/env python3
"""
Pulls every NFL QB/RB/WR/TE's per-game stat lines (passing/rushing/
receiving yards, receptions, TDs) from nflverse and writes
data/nfl-players.json.

Verified against real nflverse data while writing this: the file below
has one row per skill-position player per game, with position and team
already attached -- no per-team or per-player lookups needed, unlike the
team-stats scripts.

Source: https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats.csv
This is nflverse's full all-years combined file (~30MB) -- there isn't a
current-season-only file published yet as of when this was written (their
player-level pipeline lags behind the team-level one), so we download the
whole thing and filter to YEAR client-side. If nflverse starts publishing
a "player_stats_{YEAR}.csv" per-year file again, switch to that instead
for a much smaller download.

Run: python3 scripts/fetch_players_nfl.py
Writes: data/nfl-players.json
"""
import csv
import io
import json
import sys
import urllib.request

YEAR = 2026
STATS_URL = "https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats.csv"
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


def to_num(row, key, default=0.0):
    try:
        return float(row.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def main():
    try:
        with open(EXISTING_PATH) as f:
            players = json.load(f)
    except FileNotFoundError:
        players = {}

    req = urllib.request.Request(STATS_URL, headers={"User-Agent": "matchup-room-fetcher"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except Exception as e:
        print(f"Could not fetch nflverse player_stats.csv ({e}); leaving existing file untouched.", file=sys.stderr)
        return

    rows = [r for r in csv.DictReader(io.StringIO(raw))
            if r.get("season") == str(YEAR) and r.get("season_type") == "REG"
            and r.get("position") in SKILL_POSITIONS]

    if not rows:
        print(f"No {YEAR} regular-season player rows yet (nflverse hasn't published this "
              f"season's player data) -- leaving existing file untouched.", file=sys.stderr)
        return

    by_player = {}
    for row in rows:
        name = row.get("player_display_name") or row.get("player_name")
        if not name:
            continue
        by_player.setdefault(name, {"pos": row.get("position"), "team": row.get("recent_team"), "rows": []})
        by_player[name]["rows"].append(row)

    updated = 0
    for name, info in by_player.items():
        team_abbr = info["team"]
        games = []
        for row in sorted(info["rows"], key=lambda r: int(r.get("week", 0) or 0)):
            tds = to_num(row, "passing_tds") + to_num(row, "rushing_tds") + to_num(row, "receiving_tds")
            games.append({
                "date": f"{YEAR}-wk{row.get('week', '')}",
                "opp": f"vs {row.get('opponent_team', '')}",
                "passYds": to_num(row, "passing_yards"),
                "rushYds": to_num(row, "rushing_yards"),
                "receptions": to_num(row, "receptions"),
                "recYds": to_num(row, "receiving_yards"),
                "tds": tds,
            })
        players[name] = {
            "pos": info["pos"],
            "team": TEAM_NAME_MAP.get(team_abbr, team_abbr),
            "league": "NFL",
            "games": games,
        }
        updated += 1

    with open(EXISTING_PATH, "w") as f:
        json.dump(players, f, indent=2)
    print(f"Wrote {updated} NFL players to {EXISTING_PATH}")


if __name__ == "__main__":
    main()
