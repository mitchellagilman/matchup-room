#!/usr/bin/env python3
"""
Tracks the "Best per game" picks shown in the app's Top Bets -> Best per game
tab, separately from the big Track Record: for every upcoming game it logs ONE
top team bet (spread, moneyline or total, whichever the model likes most vs.
the market price) and, when a real sportsbook line exists, ONE top player prop.
Each pick is frozen the first time it is logged (so later line moves don't
rewrite history), then graded after the game.

The team-bet logic mirrors bestTeamBetForGame() in the site's JavaScript
(keep the two in sync):
  - spread/total probability = calibrated edge->probability curve, symmetric
    around 50%
  - moneyline win chance = normal curve on the market's expected margin nudged
    35% of the way toward the model's margin; only listed if >= 50%
  - ranked by (probability - the price's implied probability)

Props are only tracked when a real sportsbook line exists (a model-only
"line" is just the model's own number, so it can't be graded as a bet).

Run: python3 scripts/track_best_per_game.py
Writes: data/best-per-game.json
"""
import datetime
import json
import math
import os
import sys

import track_predictions as tp

OUT_PATH = "data/best-per-game.json"
MARGIN_SD = {"NFL": 13.5, "CFB": 16.0}
ML_MODEL_WEIGHT = 0.35  # how far the model may move the market's expected margin


def norm_cdf(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def edge_to_probability(edge, used_sp, league, calibration):
    cal = (calibration or {}).get(league)
    strong = cal["strong_threshold"] if cal and cal.get("calibrated") else 7
    prob = 0.5 + edge * (0.12 / strong)
    if league == "CFB" and not used_sp:
        prob = 0.5 + (prob - 0.5) * 0.6
    return max(0.5, min(0.75, prob))


def implied(american):
    dec = 1 + american / 100 if american > 0 else 1 + 100 / abs(american)
    return 1 / dec


def market_margin_for(team, opp, odds_list, league=None):
    m = tp.find_market_line(team, opp, odds_list, league)
    if not m:
        return None
    s = m.get("aSpread") if tp.team_names_match(m.get("aTeam"), team) else m.get("bSpread")
    return None if s is None else -s


def best_team_bet(g, league, teams, odds_list, players, injuries_by_team, weather_cache, calibration):
    if tp.is_cross_division_game(g, teams, league):
        return None
    proj = tp.compute_projection(g["a"], g["b"], teams, league, odds_list, players, injuries_by_team, g.get("date"), weather_cache)
    market = tp.find_market_line(g["a"], g["b"], odds_list, league)
    if not proj or not market or tp.is_extreme_mismatch(market):
        return None
    a_is_entry_a = tp.team_names_match(market.get("aTeam"), g["a"])
    opts = []
    a_spread = market.get("aSpread")
    if a_spread is not None:
        market_fav_a = -a_spread if a_is_entry_a else a_spread
        edge = proj["spread"] - market_fav_a
        team = g["a"] if edge > 0 else g["b"]
        if a_is_entry_a:
            line = market.get("aSpread") if edge > 0 else market.get("bSpread")
            odds = market.get("aSpreadOdds") if edge > 0 else market.get("bSpreadOdds")
        else:
            line = market.get("bSpread") if edge > 0 else market.get("aSpread")
            odds = market.get("bSpreadOdds") if edge > 0 else market.get("aSpreadOdds")
        price = -110 if odds is None else odds
        prob = edge_to_probability(abs(edge), proj.get("usedSP", False), league, calibration)
        opts.append({"type": "spread", "kind": "Spread", "label": f"{team} {'+' if line > 0 else ''}{line}",
                     "prob": prob, "odds": price, "edge": abs(edge), "line": line, "favored_team": team,
                     "value": prob - implied(price)})
    total = market.get("total")
    if total is not None:
        edge = proj["total"] - total
        over = edge > 0
        odds = market.get("overOdds") if over else market.get("underOdds")
        price = -110 if odds is None else odds
        prob = edge_to_probability(abs(edge), proj.get("usedSP", False), league, calibration)
        opts.append({"type": "total", "kind": "Total", "label": f"{'Over' if over else 'Under'} {total}",
                     "prob": prob, "odds": price, "edge": abs(edge), "line": total,
                     "direction": "over" if over else "under", "value": prob - implied(price)})
    sd = MARGIN_SD.get(league, 13.5)
    for team, opp, margin, ml in (
        (g["a"], g["b"], proj["spread"], market.get("aML") if a_is_entry_a else market.get("bML")),
        (g["b"], g["a"], -proj["spread"], market.get("bML") if a_is_entry_a else market.get("aML")),
    ):
        if ml is None:
            continue
        mm = market_margin_for(team, opp, odds_list, league)
        m = margin if mm is None else mm + ML_MODEL_WEIGHT * (margin - mm)
        prob = max(0.1, min(0.9, norm_cdf(m / sd)))
        if prob < 0.5:
            continue
        opts.append({"type": "ml", "kind": "Moneyline", "label": f"{team} ML", "prob": prob, "odds": ml,
                     "edge": margin, "line": 0, "favored_team": team, "value": prob - implied(ml)})
    if not opts:
        return None
    return max(opts, key=lambda o: o["value"])


def week_label(league, nfl_week, date_str):
    if league == "NFL":
        return f"NFL Week {nfl_week}" if nfl_week else f"NFL {date_str}"
    try:
        d = datetime.date.fromisoformat(date_str)
        week = max(1, (d - datetime.date(2026, 8, 29)).days // 7 + 1)
        return f"CFB Week {week}"
    except Exception:
        return f"CFB {date_str}"


def grade_ml(pick, scores):
    s = scores.get((pick.get("_away"), pick.get("_home")))
    if not s:
        return None
    a, h = s
    if a == h:
        return "push"
    won = (a > h) if pick["favored_team"] == pick["_away"] else (h > a)
    return "hit" if won else "miss"


def main():
    today = datetime.date.today().isoformat()
    teams = {}
    teams.update(tp.load_json("data/nfl-teams.json", {}))
    teams.update(tp.load_json("data/cfb-teams.json", {}))
    nfl_players = tp.load_json("data/nfl-players.json", {})
    cfb_players = tp.load_json("data/cfb-players.json", {})
    players = {}
    players.update(nfl_players)
    for name, p in cfb_players.items():
        existing = players.get(name)
        key = f"{name} (CFB)" if existing and existing.get("league") != p.get("league") else name
        players[key] = p
    inj = tp.load_json("data/nfl-injuries.json", {})
    injuries_by_team = {}
    for e in (inj.get("entries") or []):
        injuries_by_team.setdefault(e.get("team"), []).append(e)
    calibration = tp.load_json("data/calibration.json", {})
    weather_cache = tp.load_json("data/weather.json", {})
    nfl_sched = tp.load_json("data/nfl-schedule.json", {"week": None, "games": []})
    cfb_games = tp.load_json("data/cfb-schedule.json", [])
    odds_list = tp.load_json("data/nfl-week-odds.json", []) + tp.load_json("data/odds.json", [])
    props_odds = tp.load_json("data/player-props-odds.json", {})

    record = tp.load_json(OUT_PATH, {"picks": []})
    if record.get("version", 1) < 2:
        # One-time cleanup after fixing a team-name matching bug ("Indiana" was
        # matching the Indianapolis Colts' odds). Drop still-pending team picks
        # so they re-log correctly, plus any CFB Indiana team pick already made.
        record["picks"] = [p for p in record["picks"] if not (
            p.get("type") != "player_prop" and (p.get("status") == "pending" or (p.get("league") == "CFB" and "Indiana" in p.get("matchup", ""))))]
        record["version"] = 2
    existing = {p["id"] for p in record["picks"]}
    logged = 0

    sources = [("NFL", nfl_sched.get("games", []), nfl_sched.get("week")), ("CFB", cfb_games, None)]
    scores = {}
    for league, games, wk in sources:
        for g in games:
            if g.get("awayScore") is not None and g.get("homeScore") is not None:
                scores[(g["a"], g["b"])] = (float(g["awayScore"]), float(g["homeScore"]))
        upcoming = [g for g in games if g.get("awayScore") is None and g.get("homeScore") is None]
        for g in upcoming:
            date = (g.get("date") or today)[:10]
            if date < today:
                continue  # never log a pick for a game already played/underway without a score
            matchup = f"{g['a']} vs {g['b']}"
            pid = f"BPG|{league}|{date}|{matchup}|team"
            if pid not in existing:
                best = best_team_bet(g, league, teams, odds_list, players, injuries_by_team, weather_cache, calibration)
                if best:
                    pick = {
                        "id": pid, "league": league, "week": week_label(league, wk, date), "date": date,
                        "matchup": matchup, "kind": best["kind"], "type": best["type"], "label": best["label"],
                        "prob": round(best["prob"], 3), "odds": best["odds"], "edge": round(best["edge"], 1),
                        "line": best["line"], "favored_team": best.get("favored_team"), "direction": best.get("direction"),
                        "_away": g["a"], "_home": g["b"], "date_logged": today, "status": "pending", "graded_date": None,
                    }
                    record["picks"].append(pick)
                    existing.add(pid)
                    logged += 1
        # Props: one per game, only with a real sportsbook line
        try:
            cands = tp.compute_player_bets(players, teams, upcoming, league, odds_list, props_odds)
        except Exception as e:
            print(f"[{league}] prop selection failed ({e}); skipping props this run.", file=sys.stderr)
            cands = []
        by_game = {}
        for c in cands:
            if not c.get("used_real_line"):
                continue
            if c["matchup"] not in by_game or (c.get("edge") or 0) > (by_game[c["matchup"]].get("edge") or 0):
                by_game[c["matchup"]] = c
        for matchup, c in by_game.items():
            date = (c.get("game_date") or today)[:10]
            pid = f"BPG|{league}|{date}|{matchup}|prop"
            if pid in existing:
                continue
            dir_label = "Over" if c["direction"] == "over" else "Under"
            record["picks"].append({
                "id": pid, "league": league, "week": week_label(league, wk, date), "date": date,
                "matchup": matchup, "kind": "Player prop", "type": "player_prop",
                "label": f"{c['name']} {dir_label} {c['projected']} {c['stat_label']}",
                "edge": c.get("edge"), "line": c["projected"], "direction": c["direction"],
                "_player_name": c["name"], "_stat": c["stat"], "_logged_recency_key": c["_recency_key"],
                "date_logged": today, "status": "pending", "graded_date": None,
            })
            existing.add(pid)
            logged += 1

    # Grade pending picks. Scores from this run's schedule files first; fall back
    # to the full-season score sources only if something is still unresolved.
    def pending_team(league):
        return [p for p in record["picks"] if p["status"] == "pending" and p["league"] == league and p["type"] != "player_prop"]
    if pending_team("NFL") and any((p["_away"], p["_home"]) not in scores for p in pending_team("NFL")):
        scores.update(tp.fetch_nfl_final_scores(2026))
    key = os.environ.get("CFBD_API_KEY", "").strip()
    if pending_team("CFB") and any((p["_away"], p["_home"]) not in scores for p in pending_team("CFB")) and key:
        scores.update(tp.fetch_cfb_final_scores(2026, key))
    graded = 0
    for p in record["picks"]:
        if p["status"] != "pending":
            continue
        if p["type"] == "player_prop":
            res = tp.grade_player_pick(p, players)
        elif p["type"] == "ml":
            res = grade_ml(p, scores)
        else:
            res = tp.grade_team_pick(p, scores)
        if res:
            p["status"] = res
            p["graded_date"] = today
            graded += 1

    record["updated"] = today
    with open(OUT_PATH, "w") as f:
        json.dump(record, f, indent=2)
    done = [p for p in record["picks"] if p["status"] in ("hit", "miss")]
    hits = sum(1 for p in done if p["status"] == "hit")
    pct = f"{hits / len(done) * 100:.0f}%" if done else "n/a"
    print(f"Best-per-game tracker: logged {logged} new picks, graded {graded}. "
          f"Record so far: {hits}-{len(done) - hits} ({pct}) across {len(record['picks'])} picks.")


if __name__ == "__main__":
    main()