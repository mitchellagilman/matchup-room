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
meetsVolumeThreshold, capPlayersPerTeamByPosition, the L5-average-times-opponent-ratio
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

*** TRACK_LEAGUES -- RUNNING NFL AND CFB ON SEPARATE SCHEDULES ***
Set the TRACK_LEAGUES environment variable to "NFL", "CFB", or
"NFL,CFB" (the default if unset) to control which league(s) this run
processes. This exists because CFB moved to its own, less frequent
workflow schedule (Fri/Sat only, vs. NFL's 5x/week) to fit CFBD's
1,000-call/month free-tier ceiling -- without this, an NFL-only run
would still call fetch_cfb_final_scores() every time just to check for
CFB grading, wasting a CFBD call on days CFB isn't otherwise updating.

Run: CFBD_API_KEY=xxxx TRACK_LEAGUES=NFL,CFB python3 scripts/track_predictions.py
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
SHRINK_PRIOR_GAMES = 3  # mirrors index.html's SHRINK_PRIOR_GAMES -- keep in sync if it ever changes there


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def league_avg_team_stat(teams, league, key):
    vals = [t[key] for t in teams.values() if t.get("league") == league and t.get(key)]
    if not vals:
        return None
    return sum(vals) / len(vals)


def shrink_to_league_avg(raw_stat, league_avg, games_played):
    """Mirrors index.html's shrinkToLeagueAvg() -- see that function's
    comment for the full reasoning (a 1-2 game sample is extreme-outlier-
    prone, confirmed live against a real NFL turnover-margin case)."""
    if not games_played or games_played <= 0 or league_avg is None:
        return raw_stat
    return (raw_stat * games_played + league_avg * SHRINK_PRIOR_GAMES) / (games_played + SHRINK_PRIOR_GAMES)


def compute_projection(a, b, teams, league, odds_list=None):
    A, B = teams.get(a), teams.get(b)
    if not A or not B:
        return None
    home_adv = HOME_ADV.get(league, 2.0)
    a_games_played = len(A.get("games") or [])
    b_games_played = len(B.get("games") or [])
    league_avg_ppg = league_avg_team_stat(teams, league, "ppg")
    league_avg_pa = league_avg_team_stat(teams, league, "pa")
    league_avg_to = league_avg_team_stat(teams, league, "to")
    a_ppg = shrink_to_league_avg(A.get("ppg", 0), league_avg_ppg, a_games_played)
    a_pa = shrink_to_league_avg(A.get("pa", 0), league_avg_pa, a_games_played)
    a_to = shrink_to_league_avg(A.get("to", 0), league_avg_to, a_games_played)
    b_ppg = shrink_to_league_avg(B.get("ppg", 0), league_avg_ppg, b_games_played)
    b_pa = shrink_to_league_avg(B.get("pa", 0), league_avg_pa, b_games_played)
    b_to = shrink_to_league_avg(B.get("to", 0), league_avg_to, b_games_played)
    a_score = (a_ppg + b_pa) / 2 - home_adv / 2 + a_to * TO_FACTOR
    b_score = (b_ppg + a_pa) / 2 + home_adv / 2 + b_to * TO_FACTOR
    total = a_score + b_score
    spread = a_score - b_score
    market_anchored = False
    market = find_market_line(a, b, odds_list) if odds_list else None
    market_has_spread = market and market.get("aSpread") is not None
    if league == "CFB" and isinstance(A.get("spPlus"), (int, float)) and isinstance(B.get("spPlus"), (int, float)):
        # SP+ is opponent-adjusted; raw box-score ppg/pa isn't and is a
        # tiny early-season sample -- see index.html's computeProjection
        # for the full story (confirmed live: an 80-point blowout inflated
        # a team's box-score offense while barely moving their real SP+
        # rating, and a 50/50 blend let that single outlier turn a ~30-point
        # mismatch into a near-toss-up projection). Weighted toward SP+
        # rather than split evenly with the noisier box-score signal.
        sp_spread = (A["spPlus"] - B["spPlus"]) - home_adv
        spread = spread * 0.25 + sp_spread * 0.75
    elif league == "CFB" and A.get("division") and B.get("division") and A["division"] != B["division"] and market_has_spread:
        # FBS vs FCS, and a real market line exists for this specific game
        # -- see index.html's computeProjection for the full explanation
        # (confirmed live: box-score-only math produced a 35-point error on
        # a real matchup). Mirror that fix here so tracked picks don't
        # diverge from what the site actually shows.
        a_is_entry_a = team_names_match(market.get("aTeam"), a)
        market_fav_a = -market["aSpread"] if a_is_entry_a else market["aSpread"]
        spread = spread * 0.25 + market_fav_a * 0.75
        market_anchored = True
    elif league == "CFB" and isinstance(A.get("srs"), (int, float)) and isinstance(B.get("srs"), (int, float)):
        # Neither SP+ nor a usable market line was available for this game
        # -- see index.html's computeProjection for the full explanation
        # (confirmed live: a ranked FBS team vs. an FCS opponent with no
        # market line loaded fell through both safeguards above). SRS
        # covers FCS teams, unlike SP+, so it fills that gap -- trusted a
        # bit less than SP+ since it's a simpler methodology.
        srs_spread = (A["srs"] - B["srs"]) - home_adv
        spread = spread * 0.3 + srs_spread * 0.7
    a_final = round((total + spread) / 2)
    b_final = round((total - spread) / 2)
    return {"aScore": a_final, "bScore": b_final, "total": a_final + b_final, "spread": a_final - b_final, "marketAnchored": market_anchored}


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


def is_cross_division_game(g, teams, league):
    """True for an FBS-vs-FCS CFB matchup. These get excluded from Track
    Record entirely (both team bets and player props) -- per-user
    request: the model's read on these is leaning on a market line or a
    simpler SRS rating rather than a genuine head-to-head model
    projection (see computeProjection's marketAnchored/SRS branches), so
    tracking them as "predictions" and grading their accuracy isn't a
    fair test of the model itself the way a real FBS-vs-FBS pick is."""
    if league != "CFB":
        return False
    a, b = teams.get(g.get("a")), teams.get(g.get("b"))
    return bool(a and b and a.get("division") and b.get("division") and a["division"] != b["division"])


def compute_team_bets(games, teams, odds_list, league):
    """Every game's spread + total pick -- no top-N cut. (Was capped at 10
    by combined edge; that cap is what's removed here so the whole week's
    slate gets tracked, not just the model's most-confident-looking picks.)"""
    candidates = []
    for g in games:
        if is_cross_division_game(g, teams, league):
            continue
        proj = compute_projection(g["a"], g["b"], teams, league, odds_list)
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
                "game_date": g.get("date"),
            })
        total_val = market.get("total")
        if total_val is not None:
            total_edge = proj["total"] - total_val
            candidates.append({
                "type": "total", "edge": abs(total_edge),
                "label": f"{'Over' if total_edge > 0 else 'Under'} {total_val}",
                "matchup": f"{g['a']} vs {g['b']}", "direction": "over" if total_edge > 0 else "under", "line": total_val,
                "game_date": g.get("date"),
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


def round_to_half(n):
    """Mirrors index.html's roundToHalf() -- real sportsbook player-prop
    lines always land on a half-point; see that function's comment for
    the full reasoning."""
    return round(n * 2) / 2


def clamp_defense_ratio(ratio):
    """Mirrors index.html's clampDefenseRatio() -- guards against a
    small-sample defensive stat (e.g. a team's rushDef after just one
    game) swinging a projection to an unrealistic extreme. Keep this in
    sync with the JS version if the bounds ever change there."""
    return max(0.6, min(1.6, ratio))


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


POSITION_CAPS = {"QB": 1, "RB": 1, "WR": 4, "TE": 2}


def cap_players_per_team_by_position(candidates):
    """Caps how many players per team, per position, are eligible to show
    up as a "top prop" -- mirrors index.html's capPlayersPerTeamByPosition,
    see that function's comment for the full reasoning. QB (and RB, same
    treatment) ranks by recency first then volume as a tie-break; WR/TE
    rank by volume alone since the goal there is "most featured in the
    rotation," not finding one true starter."""
    by_team_pos = {}
    for c in candidates:
        cap = POSITION_CAPS.get(c["pos"])
        if cap is None:
            continue
        by_team_pos.setdefault((c["team"] or "", c["pos"]), []).append(c)

    keep_ids = set()
    for (team, pos), group in by_team_pos.items():
        if pos == "QB" or pos == "RB":
            group.sort(key=lambda c: (c["_recency_key"], c["_l5avg"]), reverse=True)
        else:
            group.sort(key=lambda c: c["_l5avg"], reverse=True)
        for c in group[: POSITION_CAPS[pos]]:
            keep_ids.add(id(c))

    return [c for c in candidates if POSITION_CAPS.get(c["pos"]) is None or id(c) in keep_ids]


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
        if len(plist) < 2:
            continue  # a single game is too thin a sample to recommend a bet on -- confirmed live: a 1-game rookie/backup sample (65 rushing yards in one game) cleared the flat volume threshold easily despite not being an established, ongoing role
        game = find_game_for_team(games, p.get("team") or "")
        if not game:
            continue
        if is_cross_division_game(game, teams, league):
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
        projected = round_to_half(l5avg * ratio)
        candidates.append({
            "name": name, "pos": p.get("pos"), "team": p.get("team"), "opp": opp,
            "matchup": f"{game['a']} vs {game['b']}",
            "stat": main_stat, "stat_label": STAT_LABELS.get(main_stat, main_stat),
            "projected": projected, "direction": "over" if ratio >= 1 else "under",
            "game_date": game.get("date"),
            "_recency_key": most_recent_game_key(p),
            "_l5avg": l5avg,
        })
    return cap_players_per_team_by_position(candidates)


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
    # TRACK_LEAGUES controls which league(s) this run processes -- lets the
    # workflow run NFL tracking on its own (more frequent) schedule and CFB
    # tracking on a separate, less frequent one, without either accidentally
    # burning a CFBD call (fetch_cfb_final_scores) on a day CFB isn't
    # otherwise updating. Defaults to both, so a manual/standalone run still
    # behaves exactly like before this option existed.
    leagues_env = (os.environ.get("TRACK_LEAGUES") or "NFL,CFB").strip().upper()
    active_leagues = {s.strip() for s in leagues_env.split(",") if s.strip()}

    teams = {}
    teams.update(load_json("data/nfl-teams.json", {}))
    teams.update(load_json("data/cfb-teams.json", {}))
    nfl_players = load_json("data/nfl-players.json", {})
    cfb_players = load_json("data/cfb-players.json", {})
    # NFL and CFB share one flat dict keyed by plain name -- a cross-league
    # name collision (confirmed live: "Caleb Williams" is both the Bears'
    # real QB and a CFB running back at New Haven) would otherwise let the
    # CFB entry silently overwrite the NFL one, same bug as index.html's
    # ensurePlayersSeeded -- see that function's comment for the full
    # story. NFL is added first so it keeps the plain name; a colliding
    # CFB entry gets a "(CFB)" suffix instead of clobbering it.
    all_players = {}
    all_players.update(nfl_players)
    for name, p in cfb_players.items():
        existing = all_players.get(name)
        key = f"{name} (CFB)" if existing and existing.get("league") != p.get("league") else name
        all_players[key] = p

    nfl_sched = load_json("data/nfl-schedule.json", {"week": None, "games": []})
    cfb_games = load_json("data/cfb-schedule.json", [])
    odds = load_json("data/odds.json", [])
    nfl_week_odds = load_json("data/nfl-week-odds.json", [])
    all_odds = nfl_week_odds + odds

    record = load_json(TRACK_PATH, {"picks": []})

    today = datetime.date.today().isoformat()
    nfl_week_label = f"NFL-Week{nfl_sched.get('week')}"
    # CFB has no stable week-number field to key off (unlike NFL's
    # nfl_sched['week']), so each pick's own game date is used instead --
    # a real game's scheduled date never changes between runs, unlike
    # today's date. Confirmed live: the previous version keyed CFB picks
    # off today's date, so the exact same real game+bet got logged again
    # under a brand new ID every single day the workflow ran, duplicating
    # entries and double (or triple, or more) counting that one game's
    # result in the accuracy stats. This constant is now only a fallback
    # for the rare case a game is missing its own date.
    cfb_week_label_fallback = f"CFB-{today}"

    existing_ids = {p["id"] for p in record["picks"]}
    logged = 0

    all_league_sources = [
        ("NFL", nfl_week_label, nfl_sched.get("games", [])),
        ("CFB", cfb_week_label_fallback, cfb_games),
    ]
    for league, week_label, games in all_league_sources:
        if league not in active_leagues:
            continue
        team_picks = compute_team_bets(games, teams, all_odds, league)
        matchup_teams = {f"{g['a']} vs {g['b']}": (g["a"], g["b"]) for g in games}
        for p in team_picks:
            pick_week_label = f"CFB-{p['game_date']}" if league == "CFB" and p.get("game_date") else week_label
            pid = f"{league}|{pick_week_label}|{p['matchup']}|{p['type']}"
            if pid in existing_ids:
                continue
            away, home = matchup_teams.get(p["matchup"], (None, None))
            record["picks"].append({
                "id": pid, "league": league, "week": pick_week_label, "matchup": p["matchup"],
                "type": p["type"], "label": p["label"], "edge": round(p["edge"], 1),
                "date_logged": today, "status": "pending", "graded_date": None,
                "_away": away, "_home": home,
                "line": p.get("line"), "favored_team": p.get("favored_team"), "direction": p.get("direction"),
            })
            existing_ids.add(pid)
            logged += 1

        player_picks = compute_player_bets(all_players, teams, games, league)
        for p in player_picks:
            pick_week_label = f"CFB-{p['game_date']}" if league == "CFB" and p.get("game_date") else week_label
            pid = f"{league}|{pick_week_label}|{p['name']}|{p['stat']}|player_prop"
            if pid in existing_ids:
                continue
            dir_label = "Over" if p["direction"] == "over" else "Under"
            record["picks"].append({
                "id": pid, "league": league, "week": pick_week_label, "matchup": p["matchup"],
                "type": "player_prop", "label": f"{p['name']} {dir_label} {p['projected']} {p['stat_label']}",
                "edge": None,
                "date_logged": today, "status": "pending", "graded_date": None,
                "_player_name": p["name"], "_stat": p["stat"], "_logged_recency_key": p["_recency_key"],
                "line": p["projected"], "direction": p["direction"],
            })
            existing_ids.add(pid)
            logged += 1

    nfl_scores = fetch_nfl_final_scores(2026) if "NFL" in active_leagues else {}
    cfb_scores = fetch_cfb_final_scores(2026, os.environ.get("CFBD_API_KEY", "").strip()) if "CFB" in active_leagues else {}
    graded = 0
    for p in record["picks"]:
        if p["status"] != "pending":
            continue
        if p["league"] not in active_leagues:
            continue  # not this run's job to grade a league it isn't processing
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
    print(f"[{'/'.join(sorted(active_leagues))}] Logged {logged} new picks, graded {graded} pending picks. Total tracked: {len(record['picks'])}")


if __name__ == "__main__":
    main()