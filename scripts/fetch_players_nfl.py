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
PREV_YEAR = YEAR - 1  # kept as a docstring/reference value; actual fallback is detected dynamically in main()
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

    all_rows_iter = list(csv.DictReader(io.StringIO(raw)))

    # nflverse's player-level file can lag behind by more than one season
    # (confirmed live: as of writing this, it stops at 2024 -- 2025 isn't
    # in there yet even though that season is long over). Rather than
    # assume "last season" means exactly YEAR-1 and come up empty, find
    # whichever season is actually the most recent one present that's
    # still before the current year, and use that as the fallback. This
    # self-corrects automatically once nflverse catches up their pipeline
    # -- no code change needed when 2025 (or later) data eventually shows up.
    available_seasons = {int(r["season"]) for r in all_rows_iter if r.get("season", "").isdigit()}
    prior_seasons = sorted(s for s in available_seasons if s < YEAR)
    fallback_year = prior_seasons[-1] if prior_seasons else None
    seasons_to_use = {str(YEAR)} | ({str(fallback_year)} if fallback_year else set())

    rows = [r for r in all_rows_iter
            if r.get("season") in seasons_to_use and r.get("season_type") == "REG"
            and r.get("position") in SKILL_POSITIONS]

    if not rows:
        print(f"No player rows found for {YEAR} or the most recent prior season ({fallback_year}) -- leaving existing file untouched.", file=sys.stderr)
        return

    # Group historical rows by player_id (gsis_id) -- NOT by name. nflverse's
    # own files don't agree on name spelling for the same person ("DJ Moore"
    # here vs "D.J. Moore" in this file, same gsis_id), so grouping by name
    # would silently split one person's history across two entries.
    by_id = {}
    for row in rows:
        pid = row.get("player_id")
        name = row.get("player_display_name") or row.get("player_name")
        if not pid or not name:
            continue
        by_id.setdefault(pid, {"pos": row.get("position"), "name": name, "rows": []})
        by_id[pid]["rows"].append(row)

    # Existing roster-confirmed entries indexed by their id, so games get
    # attached to the SAME entry fetch_nfl_rosters.py already created
    # (using its own name spelling), instead of creating a duplicate under
    # this file's spelling.
    id_to_existing_name = {v.get("_id"): k for k, v in players.items() if v.get("_id")}

    updated = 0
    for pid, info in by_id.items():
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

        # Which dict key to write under: the roster's own name spelling if
        # this person is on a current roster (matched by id), else this
        # file's own name spelling (best-effort for a player who's never
        # been on any roster this pipeline has seen -- e.g. long retired).
        name = id_to_existing_name.get(pid, info["name"])
        existing = players.get(name, {})

        # Team: only trust an existing team if it was actually confirmed by
        # THIS run's roster (teamYear == YEAR) -- not just "something was
        # there before". A player who's fallen off every active roster
        # (confirmed live: this happened to Amari Cooper) no longer gets a
        # confident current team; team_year stays unset so the UI can show
        # an honest "not on a 2026 active roster" caveat instead of a
        # silently stale one.
        team_abbr = recent_rows[-1].get("recent_team") if recent_rows else None
        if existing.get("teamYear") == YEAR:
            team = existing["team"]
            team_year = YEAR
        else:
            team = TEAM_NAME_MAP.get(team_abbr, team_abbr)
            team_year = None

        players[name] = {
            "pos": info["pos"],
            "team": team,
            "league": "NFL",
            "games": games,
            "_id": pid,
            "teamYear": team_year,
        }
        updated += 1

    with open(EXISTING_PATH, "w") as f:
        json.dump(players, f, indent=2)
    print(f"Wrote {updated} NFL players (rolling {WINDOW}-game window, {fallback_year}-{YEAR}) to {EXISTING_PATH}")


if __name__ == "__main__":
    main()
