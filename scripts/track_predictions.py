#!/usr/bin/env python3
"""
Tracks every weekly bet -- team spread/total for every game, AND player
prop projections for every qualifying player -- so real accuracy is
visible over time, instead of the app just asserting a methodology.

Each run:
1. Recomputes this week's team bets (spread + total, EVERY game, not just
   a top-N cut) and player prop bets (projected number + over/under
   direction, for every player who clears the same volume/recency
   filters used in index.html's Player Props tab), for both leagues.
2. Logs any picks not already logged this week to data/track-record.json
   with status "pending".
3. Re-checks previously "pending" picks and grades them hit/miss/push
   once that specific game (team picks) or that specific player's next
   game (player prop picks) has actually happened.

*** PORT NOTE ***
This mirrors index.html's JS model by hand -- computeProjection() for
team bets, and the Player Props matchup logic (defCategoryForStat,
meetsVolumeThreshold, dedupeStaleQBs, the L5-average-times-opponent-ratio
projection) for player bets. If any of that changes in index.html, change
it here too, or the tracked record will quietly diverge from what the app
actually shows.

*** PLAYER PROP GRADING -- READ THIS ***
There's no real sportsbook line for player props anywhere in this
pipeline (a real player-props feed was looked into and set aside -- see
project history -- it needs a much more expensive per-game API call and
CFB coverage would be thin). So a player prop pick is graded against the
model's OWN projected number: did the player's actual next-game stat
clear that projected number in the predicted direction. That's a
meaningful thing to track (is the projection itself well-calibrated) but
it is NOT "would a real bet at a real sportsbook have won" -- there's no
real line being tested. Keep that distinction in mind reading the results.

Grading a player prop works by comparing each player's "most recent
game" marker at logging time vs. now: if a newer game has been appended
to their log since the pick was made, that game is graded. This avoids
needing to reconstruct an exact date string to match against.

Run: CFBD_API_KEY=xxxx python3 scripts/track_predictions.py
Writes: data/track-record.json
"""
import csv
import io
import json
import os
import re
import sys
import urllib.request
import urllib.parse
import datetime
from cfbd_utils import cfbd_get

TRACK_PATH = "data/track-record.json"
HOME_ADV = {"NFL": 2.0, "CFB": 2.5}
TO_FACTOR = 1.5
MIN_VOLUME_FOR_BET = {"passYds": 75, "rushYds": 15, "recYds": 15}

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
STAT_LABELS = {"passYds": "passing yards", "rushYds": "rushing yards", "recYds": "receiving yards"}


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


def compute_team_bets(games, teams, odds_list, league):
    """Every game's spread + total pick -- no top-N cut. (Was capped at 10
    by combined edge; that cap is what's removed here so the whole week's
    slate gets tracked, not just the model's most-confident-looking picks.)"""
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
    return candidates


# ---- player props ----

def def_category_for_stat(stat):
    if stat == "passYds":
        return "passDef"
    if stat == "rushYds":
        return "rushDef"
    if stat in ("receptions", "recYds"):
        return "passDef"
    return None


def league_avg_def_stat(teams, league, key):
    vals = [t[key] for t in teams.values() if t.get("league") == league and t.get(key)]
    if not vals:
        return None
    return sum(vals) / len(vals)


def meets_volume_threshold(stat, l5avg):
    min_val = MIN_VOLUME_FOR_BET.get(stat)
    return min_val is None or l5avg >= min_val


def most_recent_game_key(player):
    """year*100+week of a player's last logged game, or -1 if none. Games
    are stored oldest-to-newest, so the last array entry is the newest."""
    games = (player or {}).get("games") or []
    if not games:
        return -1
    m = re.match(r"^(\d+)-wk(\d+)", games[-1].get("date", "") or "")
    if not m:
        return -1
    return int(m.group(1)) * 100 + int(m.group(2))


def dedupe_stale_qbs(candidates):
    """Only the most-recently-played QB per team stays -- see index.html's
    dedupeStaleQBs for the full reasoning (no depth-chart data anywhere in
    this pipeline, so recency is the best available stand-in for "who's
    actually starting now")."""
    best = {}
    for c in candidates:
        if c["pos"] != "QB":
            continue
        key = c["team"] or ""
        if key not in best or c["_recency_key"] > best[key]:
            best[key] = c["_recency_key"]
    return [c for c in candidates if c["pos"] != "QB" or c["_recency_key"] == best.get(c["team"] or "")]


def find_game_for_team(games, team_name):
    norm = (team_name or "").lower()
    for g in games:
        if g["a"].lower() == norm or g["b"].lower() == norm:
            return g
    return None


def compute_player_bets(players, teams, games, league):
    candidates = []
    for name, p in players.items():
        if p.get("league") != league:
            continue
        if league == "NFL" and p.get("team") and p.get("teamYear") is None:
            continue  # not on a confirmed current roster
        plist = p.get("games") or []
        if not plist:
            continue
        game = find_game_for_team(games, p.get("team") or "")
        if not game:
            continue
        opp = game["b"] if game["a"].lower() == (p.get("team") or "").lower() else game["a"]
        if opp not in teams:
            continue
        main_stat = "passYds"
        if p.get("pos") == "RB":
            main_stat = "rushYds"
        if p.get("pos") in ("WR", "TE"):
            main_stat = "recYds"
        def_key = def_category_for_stat(main_stat)
        if not def_key or not teams[opp].get(def_key):
            continue
        avg_val = league_avg_def_stat(teams, league, def_key)
        if not avg_val:
            continue
        last5 = plist[-5:]
        l5avg = sum((g.get(main_stat, 0) or 0) for g in last5) / len(last5)
        if not meets_volume_threshold(main_stat, l5avg):
            continue
        ratio = teams[opp][def_key] / avg_val
        projected = round(l5avg * ratio, 1)
        candidates.append({
            "name": name, "pos": p.get("pos"), "team": p.get("team"), "opp": opp,
            "matchup": f"{game['a']} vs {game['b']}",
            "stat": main_stat, "stat_label": STAT_LABELS.get(main_stat, main_stat),
            "projected": projected, "direction": "over" if ratio >= 1 else "under",
            "_recency_key": most_recent_game_key(p),
        })
    return dedupe_stale_qbs(candidates)


# ---- final scores (team grading) ----

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
        games = cfbd_get("/games", {"year": year, "seasonType": "regular"}, api_key)
    except Exception as e:
        print(f"Could not fetch CFB scores for grading ({e}); skipping CFB grading this run.", file=sys.stderr)
        return {}
    out = {}
    for g in games:
        if g.get("homePoints") is None:
            continue
        out[(g.get("awayTeam"), g.get("homeTeam"))] = (float(g["awayPoints"]), float(g["homePoints"]))
    return out


def grade_team_pick(pick, final_scores):
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


def grade_player_pick(pick, players):
    p = players.get(pick.get("_player_name"))
    if not p:
        return None
    current_key = most_recent_game_key(p)
    if current_key <= pick.get("_logged_recency_key", current_key):
        return None  # no new game logged for this player since the pick was made
    games = p.get("games") or []
    if not games:
        return None
    actual = games[-1].get(pick["_stat"], 0) or 0
    line = pick["line"]
    if actual == line:
        return "push"
    if pick["direction"] == "over":
        return "hit" if actual > line else "miss"
    return "hit" if actual < line else "miss"


def main():
    teams = {}
    teams.update(load_json("data/nfl-teams.json", {}))
    teams.update(load_json("data/cfb-teams.json", {}))
    nfl_players = load_json("data/nfl-players.json", {})
    cfb_players = load_json("data/cfb-players.json", {})
    all_players = {}
    all_players.update(nfl_players)
    all_players.update(cfb_players)

    nfl_sched = load_json("data/nfl-schedule.json", {"week": None, "games": []})
    cfb_games = load_json("data/cfb-schedule.json", [])
    odds = load_json("data/odds.json", [])
    nfl_week_odds = load_json("data/nfl-week-odds.json", [])
    all_odds = nfl_week_odds + odds

    record = load_json(TRACK_PATH, {"picks": []})

    today = datetime.date.today().isoformat()
    nfl_week_label = f"NFL-Week{nfl_sched.get('week')}"
    cfb_week_label = f"CFB-{today}"  # CFB's own week number isn't in cfb-schedule.json; date-based label avoids double-logging within the same day's run

    existing_ids = {p["id"] for p in record["picks"]}
    logged = 0

    for league, week_label, games in [
        ("NFL", nfl_week_label, nfl_sched.get("games", [])),
        ("CFB", cfb_week_label, cfb_games),
    ]:
        team_picks = compute_team_bets(games, teams, all_odds, league)
        matchup_teams = {f"{g['a']} vs {g['b']}": (g["a"], g["b"]) for g in games}
        for p in team_picks:
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

        player_picks = compute_player_bets(all_players, teams, games, league)
        for p in player_picks:
            pid = f"{league}|{week_label}|{p['name']}|{p['stat']}|player_prop"
            if pid in existing_ids:
                continue
            dir_label = "Over" if p["direction"] == "over" else "Under"
            record["picks"].append({
                "id": pid, "league": league, "week": week_label, "matchup": p["matchup"],
                "type": "player_prop", "label": f"{p['name']} {dir_label} {p['projected']} {p['stat_label']}",
                "edge": None,
                "date_logged": today, "status": "pending", "graded_date": None,
                "_player_name": p["name"], "_stat": p["stat"], "_logged_recency_key": p["_recency_key"],
                "line": p["projected"], "direction": p["direction"],
            })
            existing_ids.add(pid)
            logged += 1

    nfl_scores = fetch_nfl_final_scores(2026)
    cfb_scores = fetch_cfb_final_scores(2026, os.environ.get("CFBD_API_KEY", "").strip())
    graded = 0
    for p in record["picks"]:
        if p["status"] != "pending":
            continue
        if p["type"] == "player_prop":
            result = grade_player_pick(p, all_players)
        else:
            scores = nfl_scores if p["league"] == "NFL" else cfb_scores
            result = grade_team_pick(p, scores)
        if result:
            p["status"] = result
            p["graded_date"] = today
            graded += 1

    with open(TRACK_PATH, "w") as f:
        json.dump(record, f, indent=2)
    print(f"Logged {logged} new picks, graded {graded} pending picks. Total tracked: {len(record['picks'])}")


if __name__ == "__main__":
    main()
