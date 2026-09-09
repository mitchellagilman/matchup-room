#!/usr/bin/env python3
"""
Tracks Top Bets picks over time so their actual accuracy is visible,
instead of the app just asserting a methodology and hoping it's good.

Each run:
1. Recomputes this week's Top 10 picks for both leagues, using a Python
   port of index.html's computeProjection() model.
2. Logs any picks not already logged this week to data/track-record.json
   with status "pending".
3. Re-checks previously "pending" picks against actual final scores
   (pulled fresh each run) and grades them hit/miss/push once that
   specific game has actually been played.

*** PORT NOTE ***
This mirrors the JS projection math in index.html (computeProjection) by
hand. If the model changes in one place, change it in both, or Top Bets
and the tracked record will quietly diverge from each other.

Run: CFBD_API_KEY=xxxx python3 scripts/track_predictions.py
Writes: data/track-record.json
"""
import csv
import io
import json
import os
import sys
import urllib.request
import urllib.parse
import datetime

TRACK_PATH = "data/track-record.json"
HOME_ADV = {"NFL": 2.0, "CFB": 2.5}
TO_FACTOR = 1.5

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


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def compute_projection(a, b, teams, league):
    A, B = teams.get(a), teams.get(b)
    if not A or not B:
        return None
    home_adv = HOME_ADV.get(league, 2.0)
    a_score = (A.get("ppg", 0) + B.get("pa", 0)) / 2 - home_adv / 2 + A.get("to", 0) * TO_FACTOR
    b_score = (B.get("ppg", 0) + A.get("pa", 0)) / 2 + home_adv / 2 + B.get("to", 0) * TO_FACTOR
    total = a_score + b_score
    spread = a_score - b_score
    if league == "CFB" and isinstance(A.get("spPlus"), (int, float)) and isinstance(B.get("spPlus"), (int, float)):
        sp_spread = (A["spPlus"] - B["spPlus"]) - home_adv
        spread = spread * 0.5 + sp_spread * 0.5
    a_final = round((total + spread) / 2)
    b_final = round((total - spread) / 2)
    return {"aScore": a_final, "bScore": b_final, "total": a_final + b_final, "spread": a_final - b_final}


def team_names_match(a, b):
    if not a or not b:
        return False
    if a == b:
        return True
    na, nb = a.lower(), b.lower()
    return na.startswith(nb) or nb.startswith(na)


def find_market_line(a, b, odds_list):
    for o in odds_list:
        if (team_names_match(o.get("aTeam"), a) and team_names_match(o.get("bTeam"), b)) or \
           (team_names_match(o.get("aTeam"), b) and team_names_match(o.get("bTeam"), a)):
            return o
    return None


def compute_top_bets(games, teams, odds_list, league):
    candidates = []
    for g in games:
        proj = compute_projection(g["a"], g["b"], teams, league)
        if not proj:
            continue
        market = find_market_line(g["a"], g["b"], odds_list)
        if not market:
            continue
        a_is_entry_a = team_names_match(market.get("aTeam"), g["a"])
        a_spread_val = market.get("aSpread")
        if a_spread_val is not None:
            market_fav_a = -a_spread_val if a_is_entry_a else a_spread_val
            spread_edge = proj["spread"] - market_fav_a
            favored_team = g["a"] if spread_edge > 0 else g["b"]
            if a_is_entry_a:
                favored_line = market.get("aSpread") if spread_edge > 0 else market.get("bSpread")
            else:
                favored_line = market.get("bSpread") if spread_edge > 0 else market.get("aSpread")
            candidates.append({
                "type": "spread", "edge": abs(spread_edge),
                "label": f"{favored_team} {'+' if favored_line and favored_line > 0 else ''}{favored_line}",
                "matchup": f"{g['a']} vs {g['b']}", "favored_team": favored_team, "line": favored_line,
            })
        total_val = market.get("total")
        if total_val is not None:
            total_edge = proj["total"] - total_val
            candidates.append({
                "type": "total", "edge": abs(total_edge),
                "label": f"{'Over' if total_edge > 0 else 'Under'} {total_val}",
                "matchup": f"{g['a']} vs {g['b']}", "direction": "over" if total_edge > 0 else "under", "line": total_val,
            })
    candidates.sort(key=lambda c: -c["edge"])
    return candidates[:10]


def fetch_nfl_final_scores(year):
    url = "https://github.com/nflverse/nfldata/raw/master/data/games.csv"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "matchup-room-fetcher"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            rows = list(csv.DictReader(io.StringIO(resp.read().decode("utf-8"))))
    except Exception as e:
        print(f"Could not fetch NFL scores for grading ({e}); skipping NFL grading this run.", file=sys.stderr)
        return {}
    out = {}
    for r in rows:
        if r.get("season") != str(year) or r.get("game_type") != "REG":
            continue
        if not r.get("home_score"):
            continue
        home = TEAM_NAME_MAP.get(r["home_team"], r["home_team"])
        away = TEAM_NAME_MAP.get(r["away_team"], r["away_team"])
        try:
            out[(away, home)] = (float(r["away_score"]), float(r["home_score"]))
        except (TypeError, ValueError):
            continue
    return out


def fetch_cfb_final_scores(year, api_key):
    if not api_key:
        return {}
    try:
        url = f"https://api.collegefootballdata.com/games?{urllib.parse.urlencode({'year': year, 'seasonType': 'regular'})}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            games = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Could not fetch CFB scores for grading ({e}); skipping CFB grading this run.", file=sys.stderr)
        return {}
    out = {}
    for g in games:
        if g.get("homePoints") is None:
            continue
        out[(g.get("awayTeam"), g.get("homeTeam"))] = (float(g["awayPoints"]), float(g["homePoints"]))
    return out


def grade_pick(pick, final_scores):
    scores = final_scores.get((pick.get("_away"), pick.get("_home")))
    if not scores:
        return None
    ascore, hscore = scores
    if pick["type"] == "total":
        actual_total = ascore + hscore
        line = pick["line"] or 0
        if actual_total == line:
            return "push"
        if pick["direction"] == "over":
            return "hit" if actual_total > line else "miss"
        return "hit" if actual_total < line else "miss"
    elif pick["type"] == "spread":
        margin = (ascore - hscore) if pick["favored_team"] == pick.get("_away") else (hscore - ascore)
        needed = abs(pick["line"] or 0)
        if margin == needed:
            return "push"
        return "hit" if margin > needed else "miss"
    return None


def main():
    teams = {}
    teams.update(load_json("data/nfl-teams.json", {}))
    teams.update(load_json("data/cfb-teams.json", {}))

    nfl_sched = load_json("data/nfl-schedule.json", {"week": None, "games": []})
    cfb_games = load_json("data/cfb-schedule.json", [])
    odds = load_json("data/odds.json", [])
    nfl_week_odds = load_json("data/nfl-week-odds.json", [])
    all_odds = nfl_week_odds + odds

    record = load_json(TRACK_PATH, {"picks": []})

    today = datetime.date.today().isoformat()
    nfl_week_label = f"NFL-Week{nfl_sched.get('week')}"
    cfb_week_label = f"CFB-{today}"  # CFB's own week number isn't in cfb-schedule.json; date-based label avoids double-logging within the same day's run

    nfl_picks = compute_top_bets(nfl_sched.get("games", []), teams, all_odds, "NFL")
    cfb_picks = compute_top_bets(cfb_games, teams, all_odds, "CFB")

    existing_ids = {p["id"] for p in record["picks"]}
    logged = 0
    for league, week_label, picks, games in [
        ("NFL", nfl_week_label, nfl_picks, nfl_sched.get("games", [])),
        ("CFB", cfb_week_label, cfb_picks, cfb_games),
    ]:
        # matchup string -> (away, home) so grading can look up final scores later
        matchup_teams = {f"{g['a']} vs {g['b']}": (g["a"], g["b"]) for g in games}
        for p in picks:
            pid = f"{league}|{week_label}|{p['matchup']}|{p['type']}"
            if pid in existing_ids:
                continue
            away, home = matchup_teams.get(p["matchup"], (None, None))
            record["picks"].append({
                "id": pid, "league": league, "week": week_label, "matchup": p["matchup"],
                "type": p["type"], "label": p["label"], "edge": round(p["edge"], 1),
                "date_logged": today, "status": "pending", "graded_date": None,
                "_away": away, "_home": home,
                "line": p.get("line"), "favored_team": p.get("favored_team"), "direction": p.get("direction"),
            })
            existing_ids.add(pid)
            logged += 1

    nfl_scores = fetch_nfl_final_scores(2026)
    cfb_scores = fetch_cfb_final_scores(2026, os.environ.get("CFBD_API_KEY", "").strip())
    graded = 0
    for p in record["picks"]:
        if p["status"] != "pending":
            continue
        scores = nfl_scores if p["league"] == "NFL" else cfb_scores
        result = grade_pick(p, scores)
        if result:
            p["status"] = result
            p["graded_date"] = today
            graded += 1

    with open(TRACK_PATH, "w") as f:
        json.dump(record, f, indent=2)
    print(f"Logged {logged} new picks, graded {graded} pending picks. Total tracked: {len(record['picks'])}")


if __name__ == "__main__":
    main()
