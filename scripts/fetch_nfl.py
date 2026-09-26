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
        all_game_rows = fetch_csv(GAMES_URL)  # multi-season historical file -- reused below for last season's final stats too, no second fetch needed for this part
    except Exception as e:
        print(f"Could not fetch games.csv ({e}); leaving existing file untouched.", file=sys.stderr)
        return
    game_rows = [g for g in all_game_rows if g.get("season") == str(YEAR) and g.get("game_type") == "REG"]

    # Previous season's final team stats -- used as the shrinkage PRIOR
    # instead of a flat league average (see the "prev_*" fields below and
    # index.html's shrinkToLeagueAvg for how these get used). Confirmed
    # live: shrinking early-season stats toward a generic league-average
    # target meant a team with a real, multi-year track record of being
    # bad (or good) got treated as a coin-flip-average team for the first
    # few weeks of a new season, which doesn't reflect reality -- a real
    # sportsbook's opening line (e.g. a real Bills-Jets line) already
    # prices in exactly that kind of history, which this pipeline
    # previously had no way to. This isn't a perfect substitute for that
    # (a team can genuinely improve/decline between seasons), but it's a
    # much more informed prior than "assume average" for the handful of
    # weeks before this season's own sample size takes over.
    prev_game_rows = [g for g in all_game_rows if g.get("season") == str(YEAR - 1) and g.get("game_type") == "REG"]
    prev_scores_by_team = {}
    for g in prev_game_rows:
        home, away = g.get("home_team"), g.get("away_team")
        try:
            hs, as_ = float(g["home_score"]), float(g["away_score"])
        except (TypeError, ValueError, KeyError):
            continue
        prev_scores_by_team.setdefault(home, []).append({"for": hs, "against": as_})
        prev_scores_by_team.setdefault(away, []).append({"for": as_, "against": hs})

    prev_to_by_team = {}
    try:
        prev_stat_rows = fetch_csv(STATS_URL.replace(str(YEAR), str(YEAR - 1)))
        prev_offense_by_game_team = {}
        for row in prev_stat_rows:
            prev_offense_by_game_team.setdefault(row["game_id"], {})[row["team"]] = row
        prev_to_sum, prev_to_count = {}, {}
        for game_id, teams_in_game in prev_offense_by_game_team.items():
            for team, row in teams_in_game.items():
                takeaways = to_num(row, "def_interceptions") + to_num(row, "fumble_recovery_opp")
                giveaways = (to_num(row, "passing_interceptions") + to_num(row, "sack_fumbles_lost")
                             + to_num(row, "rushing_fumbles_lost") + to_num(row, "receiving_fumbles_lost"))
                prev_to_sum[team] = prev_to_sum.get(team, 0) + (takeaways - giveaways)
                prev_to_count[team] = prev_to_count.get(team, 0) + 1
        prev_to_by_team = {team: prev_to_sum[team] / prev_to_count[team] for team in prev_to_sum}
    except Exception as e:
        print(f"Could not fetch previous season's turnover stats ({e}); prevTo will be omitted, not guessed.", file=sys.stderr)

    # game_id -> team -> row, so we can look up "what did my opponent do in
    # this game" (= what I allowed).
    offense_by_game_team = {}
    for row in stat_rows:
        offense_by_game_team.setdefault(row["game_id"], {})[row["team"]] = row

    # team -> list of {points_for, points_against, week, opp}
    scores_by_team = {}
    for g in game_rows:
        home, away = g["home_team"], g["away_team"]
        try:
            hs, as_ = float(g["home_score"]), float(g["away_score"])
        except (TypeError, ValueError):
            continue  # game hasn't been played yet
        week = g.get("week")
        game_date = g.get("gameday")  # real calendar date (YYYY-MM-DD), confirmed present in nflverse's games.csv -- week number alone isn't enough to compute real rest-days between games (a Thursday game and a Sunday game can both be "week N" for their respective teams, but represent very different rest situations)
        scores_by_team.setdefault(home, []).append({"for": hs, "against": as_, "week": week, "date": game_date, "opp": away, "venue": "home"})
        scores_by_team.setdefault(away, []).append({"for": as_, "against": hs, "week": week, "date": game_date, "opp": home, "venue": "away"})

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
        wins = sum(1 for s in scores if s["for"] > s["against"])
        losses = sum(1 for s in scores if s["for"] < s["against"])
        ties = sum(1 for s in scores if s["for"] == s["against"])
        record = f"{wins}-{losses}" + (f"-{ties}" if ties else "")
        existing = teams.get(full_name, {})

        # Per-game results (opponent, week, score, W/L/T) -- shown in the
        # Teams tab when a team is clicked, and also gives the frontend a
        # real games-played count to use for early-season shrinkage (see
        # index.html's computeProjection -- a team's raw ppg/pa/turnover
        # margin from just 1-2 games is extreme-outlier-prone, confirmed
        # live: a team's whole-season turnover margin input was literally
        # just their one Week 1 game's result).
        sorted_scores = sorted(scores, key=lambda s: int(s["week"]) if (s.get("week") or "").isdigit() else 0)
        game_log = []
        for s in sorted_scores:
            result = "W" if s["for"] > s["against"] else ("L" if s["for"] < s["against"] else "T")
            game_log.append({
                "week": s.get("week"), "date": s.get("date"),
                "opp": TEAM_NAME_MAP.get(s.get("opp"), s.get("opp")),
                "teamScore": s["for"], "oppScore": s["against"], "result": result,
            })

        teams[full_name] = {
            "league": "NFL",
            "record": record if scores else existing.get("record", ""),
            "ppg": round(sum(s["for"] for s in scores) / ns, 1) if scores else existing.get("ppg", 0),
            "pa": round(sum(s["against"] for s in scores) / ns, 1) if scores else existing.get("pa", 0),
            "passOff": round(sum(g["passOff"] for g in games) / n, 1),
            "rushOff": round(sum(g["rushOff"] for g in games) / n, 1),
            "passDef": round(sum(g["passDef"] for g in games) / n, 1),
            "rushDef": round(sum(g["rushDef"] for g in games) / n, 1),
            "to": round(sum(g["to"] for g in games) / n, 2),
            "ats": existing.get("ats", ""),
            "wk1": True,
            "games": game_log if game_log else existing.get("games", []),
        }
        prev_scores = prev_scores_by_team.get(abbr)
        if prev_scores:
            teams[full_name]["prevPpg"] = round(sum(s["for"] for s in prev_scores) / len(prev_scores), 1)
            teams[full_name]["prevPa"] = round(sum(s["against"] for s in prev_scores) / len(prev_scores), 1)
        if abbr in prev_to_by_team:
            teams[full_name]["prevTo"] = round(prev_to_by_team[abbr], 2)

        # Home/away splits -- confirmed live this was a real gap: every
        # team previously got one blended ppg/pa average regardless of
        # venue, plus the same flat home-field-advantage constant applied
        # to everyone equally. A team that's genuinely much stronger at
        # home than on the road (or vice versa) wasn't reflected at all.
        # Stored here; index.html/track_predictions.py decide how much to
        # trust these vs. the season-wide number based on how many home
        # (or away) games actually exist yet -- early season, that's often
        # just 1-2, so this needs its own shrinkage, not blind trust.
        home_scores = [s for s in scores if s["venue"] == "home"]
        away_scores = [s for s in scores if s["venue"] == "away"]
        if home_scores:
            teams[full_name]["homePpg"] = round(sum(s["for"] for s in home_scores) / len(home_scores), 1)
            teams[full_name]["homePa"] = round(sum(s["against"] for s in home_scores) / len(home_scores), 1)
            teams[full_name]["homeGames"] = len(home_scores)
        if away_scores:
            teams[full_name]["awayPpg"] = round(sum(s["for"] for s in away_scores) / len(away_scores), 1)
            teams[full_name]["awayPa"] = round(sum(s["against"] for s in away_scores) / len(away_scores), 1)
            teams[full_name]["awayGames"] = len(away_scores)

    with open(EXISTING_PATH, "w") as f:
        json.dump(teams, f, indent=2)
    print(f"Wrote {len(teams)} NFL teams to {EXISTING_PATH}")


if __name__ == "__main__":
    main()