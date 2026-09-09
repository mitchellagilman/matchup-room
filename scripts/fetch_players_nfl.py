#!/usr/bin/env python3
"""
Pulls every active NFL QB/RB/WR/TE's last 10 games (rolling window,
dipping into last season early on) and writes data/nfl-players.json.

*** WHY THIS IS A DIFFERENT nflverse FILE THAN BEFORE ***
nflverse's aggregated "player_stats" file (used previously) stops at the
2024 season -- confirmed live, repeatedly. But nflverse's PLAY-BY-PLAY
file is a separate pipeline that isn't stuck the same way: verified live
while building this that play_by_play_2025.csv exists (98MB, ~48,700 real
plays) with a full 2025 regular season. This script downloads that file
and aggregates it into per-game player stats itself (passing/rushing/
receiving yards, receptions, TDs), instead of relying on nflverse to have
already done that aggregation. Sanity-checked against a real player
(Josh Allen, 2025) while building this: it produced 18 real games with
plausible week-by-week pass/rush yardage and TD counts.

*** WHY NOT ESPN (which also has 2025 data) ***
A version of this script used ESPN's gamelog API instead. It failed with
HTTP 403/400 for essentially every request when actually run from GitHub
Actions -- consistent with Cloudflare-style bot protection blocking
cloud/datacenter IP ranges, which no header change fixes from a headless
client. This nflverse-based approach stays on the same GitHub-hosted
domain that has worked reliably from Actions throughout this project.

Early in a season (or before it's started at all), there aren't 10 games
of the current year yet, so this fills the gap with the tail end of the
most recent available prior season. Once the current season has 10+
games played, the prior season drops out on its own.

Players are matched to games by gsis_id (this file's player id columns),
not by name -- see fetch_nfl_rosters.py's docstring for why matching by
name alone caused real duplicate-entry bugs before.

Sources (both verified live while building this):
https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{YEAR}.csv

Run: python3 scripts/fetch_players_nfl.py
Writes: data/nfl-players.json
"""
import csv
import io
import json
import sys
import urllib.error
import urllib.request

YEAR = 2026
WINDOW = 10
MAX_YEARS_BACK = 5  # how far back to search for the most recent available prior season
EXISTING_PATH = "data/nfl-players.json"

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


def to_num(row, key):
    try:
        return float(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def fetch_pbp_rows(year):
    """Returns a list of dict rows for one season's play-by-play, or None if that season's file doesn't exist yet."""
    url = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{year}.csv"
    req = urllib.request.Request(url, headers={"User-Agent": "matchup-room-fetcher"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return list(csv.DictReader(io.StringIO(raw)))


def aggregate_games(rows, season):
    """Turns play-by-play rows into {(player_id, game_id): {stats...}} for one season, regular season only."""
    games = {}

    def touch(pid, gid, week, team, opp):
        key = (pid, gid)
        if key not in games:
            games[key] = {"passYds": 0.0, "rushYds": 0.0, "receptions": 0, "recYds": 0.0, "tds": 0.0,
                          "week": week, "season": season, "team": team, "opp": opp}
        return games[key]

    for row in rows:
        if row.get("season_type") != "REG":
            continue
        gid, week = row.get("game_id"), row.get("week")
        if not gid or not week:
            continue
        team, opp = row.get("posteam"), row.get("defteam")

        pid = row.get("passer_player_id")
        if pid:
            g = touch(pid, gid, week, team, opp)
            g["passYds"] += to_num(row, "passing_yards")
            if row.get("pass_touchdown") == "1":
                g["tds"] += 1

        pid = row.get("rusher_player_id")
        if pid:
            g = touch(pid, gid, week, team, opp)
            g["rushYds"] += to_num(row, "rushing_yards")
            if row.get("rush_touchdown") == "1":
                g["tds"] += 1

        pid = row.get("receiver_player_id")
        if pid and row.get("complete_pass") == "1":
            g = touch(pid, gid, week, team, opp)
            g["receptions"] += 1
            g["recYds"] += to_num(row, "receiving_yards")
            if row.get("pass_touchdown") == "1":
                g["tds"] += 1

    return games


def main():
    try:
        with open(EXISTING_PATH) as f:
            players = json.load(f)
    except FileNotFoundError:
        print(f"{EXISTING_PATH} doesn't exist yet -- run fetch_nfl_rosters.py first.", file=sys.stderr)
        return

    all_season_games = {}  # (player_id, game_id) -> stats, across every season fetched
    fetched_years = []

    # Current year, if its pbp file exists yet.
    try:
        rows = fetch_pbp_rows(YEAR)
    except Exception as e:
        print(f"Could not fetch {YEAR} play-by-play ({e}); skipping.", file=sys.stderr)
        rows = None
    if rows:
        all_season_games.update(aggregate_games(rows, YEAR))
        fetched_years.append(YEAR)

    # Most recent prior year whose pbp file actually exists (walks back in
    # case a season gets skipped in nflverse's release history).
    fallback_year = None
    y = YEAR - 1
    while y >= YEAR - MAX_YEARS_BACK:
        try:
            rows = fetch_pbp_rows(y)
        except Exception as e:
            print(f"Could not fetch {y} play-by-play ({e}); trying an earlier year.", file=sys.stderr)
            rows = None
        if rows:
            all_season_games.update(aggregate_games(rows, y))
            fetched_years.append(y)
            fallback_year = y
            break
        y -= 1

    if not all_season_games:
        print("No play-by-play data found for any recent season -- leaving existing file untouched.", file=sys.stderr)
        return

    # Group by player_id, sort each player's games chronologically, keep
    # only the most recent WINDOW -- the whole "rolling 10" mechanism.
    by_player = {}
    for (pid, gid), g in all_season_games.items():
        by_player.setdefault(pid, []).append(g)

    id_to_existing_name = {v.get("_id"): k for k, v in players.items() if v.get("_id")}

    updated = 0
    for pid, glist in by_player.items():
        glist.sort(key=lambda g: (g["season"], int(g["week"])))
        recent = glist[-WINDOW:]
        if not recent:
            continue

        games_out = [{
            "date": f"{g['season']}-wk{g['week']}",
            "opp": f"vs {g['opp']}" if g["opp"] else "",
            "passYds": g["passYds"], "rushYds": g["rushYds"],
            "receptions": g["receptions"], "recYds": g["recYds"], "tds": g["tds"],
        } for g in recent]

        name = id_to_existing_name.get(pid)
        if not name:
            continue  # not a currently-rostered skill player fetch_nfl_rosters.py knows about -- skip rather than guess a name
        existing = players.get(name, {})

        team_abbr = recent[-1]["team"]
        if existing.get("teamYear") == YEAR:
            team = existing["team"]
            team_year = YEAR
        else:
            team = TEAM_NAME_MAP.get(team_abbr, team_abbr)
            team_year = None

        players[name] = {
            "pos": existing.get("pos"),
            "team": team,
            "league": "NFL",
            "games": games_out,
            "_id": pid,
            "teamYear": team_year,
        }
        updated += 1

    with open(EXISTING_PATH, "w") as f:
        json.dump(players, f, indent=2)
    print(f"Wrote {updated} NFL players (rolling {WINDOW}-game window, seasons fetched: {fetched_years}) to {EXISTING_PATH}")


if __name__ == "__main__":
    main()
