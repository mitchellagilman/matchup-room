#!/usr/bin/env python3
"""
Pulls every NFL QB/RB/WR/TE's per-game stat lines (passing/rushing/
receiving yards, receptions, TDs) from nflverse and writes
data/nfl-players.json -- keeping a rolling window of each player's most
recent 10 REGULAR SEASON games.

Early in a season (or before it's started at all), there aren't 10 games
of the current year yet, so this fills the gap with the tail end of last
season -- e.g. in Week 3, a player's window is their last 7 games of last
season plus this season's 3. Once the current season has 10+ games
played, last season drops out entirely on its own (it's just whichever
10 games are chronologically most recent -- no special "roll off" logic
needed beyond sorting and slicing).

IMPORTANT: team assignment is NOT taken from this historical data. If the
player already has a "team" set (from fetch_nfl_rosters.py, which reads
the actual current roster), that's kept as-is -- a player's team last
season isn't necessarily their team now (this is exactly the bug that
had Mack Hollins showing on Buffalo instead of New England). This script
only touches the games/trend history, never overwrites a known-current
team with a historical one.

Source: https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats.csv
This is nflverse's full all-years combined file (~30MB) -- there isn't a
current-season-only file published as of when this was written, so we
download the whole thing and filter client-side.

Run: python3 scripts/fetch_players_nfl.py
Writes: data/nfl-players.json
"""
import csv
import io
import json
import sys
import urllib.request

YEAR = 2026
PREV_YEAR = YEAR - 1
WINDOW = 10
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
            if r.get("season") in (str(YEAR), str(PREV_YEAR)) and r.get("season_type") == "REG"
            and r.get("position") in SKILL_POSITIONS]

    if not rows:
        print(f"No {PREV_YEAR}/{YEAR} regular-season player rows found at all -- leaving existing file untouched.", file=sys.stderr)
        return

    by_player = {}
    for row in rows:
        name = row.get("player_display_name") or row.get("player_name")
        if not name:
            continue
        by_player.setdefault(name, {"pos": row.get("position"), "rows": []})
        by_player[name]["rows"].append(row)

    updated = 0
    for name, info in by_player.items():
        # Sort oldest-to-newest across both seasons, then keep only the
        # most recent WINDOW games -- this is the whole "rolling 10" trick.
        sorted_rows = sorted(info["rows"], key=lambda r: (int(r.get("season", 0) or 0), int(r.get("week", 0) or 0)))
        recent_rows = sorted_rows[-WINDOW:]

        games = []
        for row in recent_rows:
            tds = to_num(row, "passing_tds") + to_num(row, "rushing_tds") + to_num(row, "receiving_tds")
            games.append({
                "date": f"{row.get('season')}-wk{row.get('week', '')}",
                "opp": f"vs {row.get('opponent_team', '')}",
                "passYds": to_num(row, "passing_yards"),
                "rushYds": to_num(row, "rushing_yards"),
                "receptions": to_num(row, "receptions"),
                "recYds": to_num(row, "receiving_yards"),
                "tds": tds,
            })

        # Team: keep whatever's already there (set by fetch_nfl_rosters.py
        # from the real current roster) if present; only fall back to the
        # historical data's team for a brand-new player we've never seen.
        existing = players.get(name, {})
        team_abbr = recent_rows[-1].get("recent_team") if recent_rows else None
        team = existing.get("team") or TEAM_NAME_MAP.get(team_abbr, team_abbr)

        players[name] = {
            "pos": info["pos"],
            "team": team,
            "league": "NFL",
            "games": games,
        }
        updated += 1

    with open(EXISTING_PATH, "w") as f:
        json.dump(players, f, indent=2)
    print(f"Wrote {updated} NFL players (rolling {WINDOW}-game window, {PREV_YEAR}-{YEAR}) to {EXISTING_PATH}")


if __name__ == "__main__":
    main()
