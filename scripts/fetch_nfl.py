#!/usr/bin/env python3
"""
Pulls current-season NFL team stats from nflverse (free, no API key) and
writes data/nfl-teams.json in the shape the site expects.

Verified against nflverse's actual published files (checked live while
writing this):
  - Per-game offensive stats, one row per team per game, with an
    opponent_team + game_id column:
    https://github.com/nflverse/nflverse-data/releases/download/stats_team/stats_team_week_{YEAR}.csv
  - Scores/schedule:
    https://github.com/nflverse/nfldata/raw/master/data/games.csv

Neither file has a "yards allowed" column directly -- nflverse only
publishes each team's own offensive output per game. Defense-allowed is
computed the same way it has to be: for team X in game G, find the OTHER
team's row in game G and use THEIR passing/rushing yards as what X
allowed. That's what the OPP_LOOKUP step below does.

If nflverse hasn't published a file for the current season yet (e.g. the
season hasn't started), this script leaves the existing data/nfl-teams.json
untouched rather than erroring out or writing zeros.

Run: python3 scripts/fetch_nfl.py
Writes: data/nfl-teams.json
"""
import csv
import io
import json
import sys
import urllib.request

YEAR = 2026
STATS_URL = f"https://github.com/nflverse/nflverse-data/releases/download/stats_team/stats_team_week_{YEAR}.csv"
GAMES_URL = "https://github.com/nflverse/nfldata/raw/master/data/games.csv"
EXISTING_PATH = "data/nfl-teams.json"

# nflverse uses "LA" for the Rams (not "LAR") -- this tripped up an earlier
# version of this script; verified against the live file.
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


def to_num(row, key, default=0.0):
    try:
        return float(row.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def main():
    try:
        with open(EXISTING_PATH) as f:
            teams = json.load(f)
    except FileNotFoundError:
        teams = {}

    try:
        stat_rows = fetch_csv(STATS_URL)
    except Exception as e:
        print(f"No nflverse stats file for {YEAR} yet ({e}); leaving existing file untouched.", file=sys.stderr)
        return

    try:
        game_rows = [g for g in fetch_csv(GAMES_URL) if g.get("season") == str(YEAR) and g.get("game_type") == "REG"]
    except Exception as e:
        print(f"Could not fetch games.csv ({e}); leaving existing file untouched.", file=sys.stderr)
        return

    # game_id -> team -> row, so we can look up "what did my opponent do in
    # this game" (= what I allowed).
    offense_by_game_team = {}
    for row in stat_rows:
        offense_by_game_team.setdefault(row["game_id"], {})[row["team"]] = row

    # team -> list of {points_for, points_against}
    scores_by_team = {}
    for g in game_rows:
        home, away = g["home_team"], g["away_team"]
        try:
            hs, as_ = float(g["home_score"]), float(g["away_score"])
        except (TypeError, ValueError):
            continue  # game hasn't been played yet
        scores_by_team.setdefault(home, []).append({"for": hs, "against": as_})
        scores_by_team.setdefault(away, []).append({"for": as_, "against": hs})

    per_team = {}  # team -> list of per-game dicts
    for game_id, teams_in_game in offense_by_game_team.items():
        for team, row in teams_in_game.items():
            opp = row.get("opponent_team")
            opp_row = teams_in_game.get(opp)
            if not opp_row:
                continue
            takeaways = to_num(row, "def_interceptions") + to_num(row, "fumble_recovery_opp")
            giveaways = (to_num(row, "passing_interceptions") + to_num(row, "sack_fumbles_lost")
                         + to_num(row, "rushing_fumbles_lost") + to_num(row, "receiving_fumbles_lost"))
            per_team.setdefault(team, []).append({
                "passOff": to_num(row, "passing_yards"),
                "rushOff": to_num(row, "rushing_yards"),
                "passDef": to_num(opp_row, "passing_yards"),   # opponent's offense = what I allowed
                "rushDef": to_num(opp_row, "rushing_yards"),
                "to": takeaways - giveaways,
            })

    for abbr, games in per_team.items():
        n = len(games) or 1
        full_name = TEAM_NAME_MAP.get(abbr, abbr)
        scores = scores_by_team.get(abbr, [])
        ns = len(scores) or 1
        existing = teams.get(full_name, {})
        teams[full_name] = {
            "league": "NFL",
            "ppg": round(sum(s["for"] for s in scores) / ns, 1) if scores else existing.get("ppg", 0),
            "pa": round(sum(s["against"] for s in scores) / ns, 1) if scores else existing.get("pa", 0),
            "passOff": round(sum(g["passOff"] for g in games) / n, 1),
            "rushOff": round(sum(g["rushOff"] for g in games) / n, 1),
            "passDef": round(sum(g["passDef"] for g in games) / n, 1),
            "rushDef": round(sum(g["rushDef"] for g in games) / n, 1),
            "to": round(sum(g["to"] for g in games) / n, 2),
            "ats": existing.get("ats", ""),
            "wk1": True,
        }

    with open(EXISTING_PATH, "w") as f:
        json.dump(teams, f, indent=2)
    print(f"Wrote {len(teams)} NFL teams to {EXISTING_PATH}")


if __name__ == "__main__":
    main()