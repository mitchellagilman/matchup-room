#!/usr/bin/env python3
"""
Pulls the current week's NFL schedule from nflverse (free, no key) and
writes data/nfl-schedule.json. "Current week" is auto-detected as the
earliest 2026 regular-season week that still has unplayed games -- so this
naturally advances Sept 9 -> Sept 15 -> etc. as the season goes, no manual
week number to maintain.

Bonus: nflverse's games.csv already carries the actual spread/total/
moneyline lines for each game (even future ones), so this also writes
data/nfl-week-odds.json as a free alternative/supplement to the Odds API
pull in fetch_odds.py.

Source (verified live): https://github.com/nflverse/nfldata/raw/master/data/games.csv

Run: python3 scripts/fetch_nfl_schedule.py
Writes: data/nfl-schedule.json, data/nfl-week-odds.json
"""
import csv
import io
import json
import sys
import urllib.request

YEAR = 2026
GAMES_URL = "https://github.com/nflverse/nfldata/raw/master/data/games.csv"
SCHEDULE_PATH = "data/nfl-schedule.json"
ODDS_PATH = "data/nfl-week-odds.json"

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
        rows = fetch_csv(GAMES_URL)
    except Exception as e:
        print(f"Could not fetch games.csv ({e}); leaving existing schedule file untouched.", file=sys.stderr)
        return

    season_rows = [r for r in rows if r.get("season") == str(YEAR) and r.get("game_type") == "REG"]
    if not season_rows:
        print(f"No {YEAR} schedule published yet; leaving existing file untouched.", file=sys.stderr)
        return

    # Current week = the earliest week that ISN'T essentially finished --
    # see the matching (and more detailed) comment in fetch_cfb_schedule.py
    # for why "most recently started week" isn't enough on its own.
    import datetime
    today = datetime.datetime.now(datetime.timezone.utc).date()
    games_by_week = {}
    for r in season_rows:
        wk = r.get("week")
        if not wk:
            continue
        games_by_week.setdefault(int(wk), []).append(r)

    current_week = None
    for wk in sorted(games_by_week.keys()):
        wk_games = games_by_week[wk]
        dates = []
        for r in wk_games:
            gameday = r.get("gameday")
            if not gameday:
                continue
            try:
                dates.append(datetime.date.fromisoformat(gameday))
            except ValueError:
                pass
        last_date = max(dates) if dates else None
        completed = sum(1 for r in wk_games if r.get("home_score"))
        completion_ratio = (completed / len(wk_games)) if wk_games else 0
        still_relevant = (last_date is None) or (today <= last_date) or (completion_ratio < 0.8)
        if still_relevant:
            current_week = wk
            break
    if current_week is None:
        current_week = max(games_by_week.keys()) if games_by_week else 1

    week_games = [r for r in season_rows if int(r["week"]) == current_week]

    schedule = []
    odds = []
    for g in week_games:
        away = TEAM_NAME_MAP.get(g["away_team"], g["away_team"])
        home = TEAM_NAME_MAP.get(g["home_team"], g["home_team"])
        date_str = f"{g.get('gameday','')} ({g.get('weekday','')})"

        def to_score(key):
            try:
                return float(g.get(key))
            except (TypeError, ValueError):
                return None

        away_score, home_score = to_score("away_score"), to_score("home_score")
        game_entry = {"a": away, "b": home, "date": date_str}
        if away_score is not None and home_score is not None:
            # Game's already been played -- carry the real result so the UI
            # can show "FINAL 24-17" instead of a hypothetical model
            # projection for a game that's already over.
            game_entry["awayScore"] = away_score
            game_entry["homeScore"] = home_score
        schedule.append(game_entry)

        def to_f(key):
            try:
                return float(g.get(key))
            except (TypeError, ValueError):
                return None

        spread = to_f("spread_line")
        total = to_f("total_line")
        away_ml = to_f("away_moneyline")
        home_ml = to_f("home_moneyline")
        if spread is not None or total is not None:
            odds.append({
                "game": f"{away} @ {home}", "league": "NFL", "date": g.get("gameday", ""),
                "aTeam": away, "aML": away_ml, "aSpread": spread, "aSpreadOdds": to_f("away_spread_odds"),
                "bTeam": home, "bML": home_ml, "bSpread": (-spread if spread is not None else None), "bSpreadOdds": to_f("home_spread_odds"),
                "total": total, "overOdds": to_f("over_odds"), "underOdds": to_f("under_odds"),
            })

    with open(SCHEDULE_PATH, "w") as f:
        json.dump({"week": current_week, "games": schedule}, f, indent=2)
    with open(ODDS_PATH, "w") as f:
        json.dump(odds, f, indent=2)
    print(f"Week {current_week}: wrote {len(schedule)} games to {SCHEDULE_PATH} and {len(odds)} lines to {ODDS_PATH}")


if __name__ == "__main__":
    main()
