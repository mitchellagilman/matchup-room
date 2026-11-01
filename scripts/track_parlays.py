#!/usr/bin/env python3
"""
Builds and tracks the "Recommended parlays": 5 per league per week (NFL and
college each), ranked by strength, then grades them after the games.

The five (when enough games are available):
  - 2 x "Sides"   : spreads / moneylines only (3 legs each, different games)
  - 2 x "Totals"  : overs / unders only (3 legs each, different games)
  - 1 x "Mix"     : best side + best total + the best real-line player props

Rules that keep them sensible:
  - one leg per game within a parlay (spread and total from the same game
    are not independent, so they never share a parlay)
  - legs where the model and market disagree by 7+ points are skipped (those
    have hit worse historically)
  - moneylines only when the team is the favorite and the price is no worse
    than -350 (huge favorites add almost no payout)
  - player props only when a real sportsbook line exists, priced from the
    book's actual over/under price
  - Strength = the average win chance of the legs (Strong >= 62%,
    Medium >= 57%, otherwise Lean). Parlays are listed strongest first.

Each week's parlays are frozen the first time they are created, then each leg
and the parlay are graded after the games. Parlay record is kept separate
from the main Track Record.

Run: python3 scripts/track_parlays.py
Writes: data/recommended-parlays.json
"""
import datetime
import json
import os
import sys

import track_predictions as tp
import track_best_per_game as bpg

OUT_PATH = "data/recommended-parlays.json"
VERSION = 1
LEGS_PER_PARLAY = 3
STRONG, MEDIUM = 0.62, 0.57
MAX_FAV_PRICE = -350


def dec(american):
    return 1 + american / 100 if american > 0 else 1 + 100 / abs(american)


def to_american(decimal):
    if decimal >= 2:
        return int(round((decimal - 1) * 100))
    return int(round(-100 / (decimal - 1)))


def prop_prob(model_proj, line):
    """Rough win chance for a real-line prop from the gap vs the line. The
    model has no validated prop probability, so this is deliberately modest."""
    if not line:
        return 0.52
    return max(0.52, min(0.58, 0.5 + 0.4 * abs(model_proj - line) / abs(line)))


def prop_price(books, line, direction):
    for b in books or []:
        if b.get("line") == line:
            p = b.get("overPrice" if direction == "over" else "underPrice")
            if p is not None:
                return p
    return -115


def team_leg(o, g, date):
    return {
        "kind": o["kind"], "type": o["type"], "label": o["label"], "matchup": f"{g['a']} vs {g['b']}",
        "date": date, "odds": int(o["odds"]), "prob": round(o["prob"], 3), "line": o["line"],
        "favored_team": o.get("favored_team"), "direction": o.get("direction"),
        "_away": g["a"], "_home": g["b"], "status": "pending",
        "meta": {"league": o["league"], "type": o["type"], "team": o.get("favored_team") or g["a"],
                 "opp": g["b"] if (o.get("favored_team") or g["a"]) == g["a"] else g["a"],
                 "line": o["line"], "dir": o.get("direction")},
    }


def strength_label(avg):
    return "Strong" if avg >= STRONG else ("Medium" if avg >= MEDIUM else "Lean")


def make_parlay(kind, name, legs, league, week, today):
    avg = sum(l["prob"] for l in legs) / len(legs)
    comb_prob = 1.0
    comb_dec = 1.0
    for l in legs:
        comb_prob *= l["prob"]
        comb_dec *= dec(l["odds"])
    return {
        "league": league, "week": week, "kind": kind, "name": name, "legs": legs,
        "avg_prob": round(avg, 3), "combined_prob": round(comb_prob, 3),
        "combined_odds": to_american(comb_dec), "strength": strength_label(avg),
        "date_logged": today, "status": "pending", "graded_date": None,
    }


def pick_distinct(cands, n, exclude_games=()):
    out, used = [], set(exclude_games)
    for c in cands:
        if c["_game"] in used:
            continue
        out.append(c)
        used.add(c["_game"])
        if len(out) == n:
            break
    return out


def build_for_league(league, games, ctx, today, week_name):
    teams, odds_list, players, inj, weather, calib, props_odds = ctx
    sides, totals, game_best = [], [], {}
    for g in games:
        date = (g.get("date") or today)[:10]
        if date < today or g.get("awayScore") is not None:
            continue
        opts = bpg.team_options(g, league, teams, odds_list, players, inj, weather, calib)
        key = f"{g['a']} vs {g['b']}"
        for o in opts:
            o["league"] = league
            if o.get("big_gap"):
                continue
            leg = team_leg(o, g, date)
            leg["_game"] = key
            if o["type"] == "total":
                if o["prob"] >= 0.53:
                    totals.append(leg)
            elif o["type"] == "spread":
                if o["prob"] >= 0.53:
                    sides.append(leg)
            elif o["type"] == "ml":
                # only when the price is roughly fair for the win chance
                if o["prob"] >= 0.6 and o["odds"] >= MAX_FAV_PRICE and o["value"] >= -0.03:
                    sides.append(leg)
    # one best side per game
    best_side = {}
    for l in sides:
        if l["_game"] not in best_side or l["prob"] > best_side[l["_game"]]["prob"]:
            best_side[l["_game"]] = l
    sides = sorted(best_side.values(), key=lambda l: -l["prob"])
    best_tot = {}
    for l in totals:
        if l["_game"] not in best_tot or l["prob"] > best_tot[l["_game"]]["prob"]:
            best_tot[l["_game"]] = l
    totals = sorted(best_tot.values(), key=lambda l: -l["prob"])

    # real-line props, one per game
    upcoming = [g for g in games if (g.get("date") or today)[:10] >= today and g.get("awayScore") is None]
    prop_legs = []
    try:
        cands = tp.compute_player_bets(players, teams, upcoming, league, odds_list, props_odds)
    except Exception as e:
        print(f"[{league}] props unavailable for parlays ({e})", file=sys.stderr)
        cands = []
    best_prop = {}
    for c in cands:
        if not c.get("used_real_line") or not c.get("edge"):
            continue
        if c["matchup"] not in best_prop or c["edge"] > best_prop[c["matchup"]]["edge"]:
            best_prop[c["matchup"]] = c
    for matchup, c in best_prop.items():
        d = c["direction"]
        price = prop_price(c.get("books"), c["projected"], d)
        prop_legs.append({
            "kind": "Player prop", "type": "player_prop", "_game": matchup, "matchup": matchup,
            "label": f"{c['name']} {'Over' if d == 'over' else 'Under'} {c['projected']} {c['stat_label']}",
            "date": (c.get("game_date") or today)[:10], "odds": int(price),
            "prob": round(prop_prob(c["model_projection"], c["projected"]), 3), "line": c["projected"],
            "direction": d, "_player_name": c["name"], "_stat": c["stat"],
            "_logged_recency_key": c["_recency_key"], "status": "pending", "meta": None, "edge": c["edge"],
        })
    prop_legs.sort(key=lambda l: -l["edge"] / max(1, abs(l["line"])))

    made = []
    s1 = pick_distinct(sides, LEGS_PER_PARLAY)
    if len(s1) >= 2:
        made.append(make_parlay("sides", "Sides A", s1, league, week_name, today))
        s2 = pick_distinct(sides, LEGS_PER_PARLAY, {l["_game"] for l in s1})
        if len(s2) >= 2:
            made.append(make_parlay("sides", "Sides B", s2, league, week_name, today))
    t1 = pick_distinct(totals, LEGS_PER_PARLAY)
    if len(t1) >= 2:
        made.append(make_parlay("totals", "Totals A", t1, league, week_name, today))
        t2 = pick_distinct(totals, LEGS_PER_PARLAY, {l["_game"] for l in t1})
        if len(t2) >= 2:
            made.append(make_parlay("totals", "Totals B", t2, league, week_name, today))
    mix = []
    if sides:
        mix.append(sides[0])
    if totals:
        t = next((l for l in totals if not mix or l["_game"] != mix[0]["_game"]), None)
        if t:
            mix.append(t)
    games_used = {l["_game"] for l in mix}
    for p in prop_legs:
        if p["_game"] in games_used:
            continue
        mix.append(p)
        games_used.add(p["_game"])
        if len(mix) >= 4:
            break
    if len(mix) >= 3 and any(l["type"] == "player_prop" for l in mix):
        made.append(make_parlay("mix", "Mix + props", mix, league, week_name, today))
    made.sort(key=lambda p: -p["avg_prob"])
    for i, p in enumerate(made, 1):
        p["rank"] = i
        p["id"] = f"PAR|{league}|{week_name}|{p['kind']}|{p['name']}"
    for p in made:
        for l in p["legs"]:
            l.pop("_game", None)
    return made


def grade_leg(leg, scores, players):
    if leg["type"] == "player_prop":
        return tp.grade_player_pick(leg, players)
    if leg["type"] == "ml":
        return bpg.grade_ml(leg, scores)
    return tp.grade_team_pick(leg, scores)


def parlay_status(legs):
    sts = [l["status"] for l in legs]
    if "miss" in sts:
        return "miss"
    if "pending" in sts:
        return "pending"
    live = [s for s in sts if s == "hit"]
    return "hit" if live else "push"


def main():
    today = datetime.date.today().isoformat()
    teams = {}
    teams.update(tp.load_json("data/nfl-teams.json", {}))
    teams.update(tp.load_json("data/cfb-teams.json", {}))
    players = {}
    nfl_players = tp.load_json("data/nfl-players.json", {})
    players.update(nfl_players)
    for name, p in tp.load_json("data/cfb-players.json", {}).items():
        ex = players.get(name)
        players[f"{name} (CFB)" if ex and ex.get("league") != p.get("league") else name] = p
    inj_raw = tp.load_json("data/nfl-injuries.json", {})
    inj = {}
    for e in (inj_raw.get("entries") or []):
        inj.setdefault(e.get("team"), []).append(e)
    calib = tp.load_json("data/calibration.json", {})
    weather = tp.load_json("data/weather.json", {})
    props_odds = tp.load_json("data/player-props-odds.json", {})
    odds_list = tp.load_json("data/nfl-week-odds.json", []) + tp.load_json("data/odds.json", [])
    nfl_sched = tp.load_json("data/nfl-schedule.json", {"week": None, "games": []})
    cfb_games = tp.load_json("data/cfb-schedule.json", [])
    ctx = (teams, odds_list, players, inj, weather, calib, props_odds)

    record = tp.load_json(OUT_PATH, {"version": VERSION, "parlays": []})
    existing = {p["id"] for p in record["parlays"]}
    created = 0

    nfl_week = bpg.week_label("NFL", nfl_sched.get("week"), today)
    upcoming_cfb_dates = sorted((g.get("date") or "")[:10] for g in cfb_games
                                if g.get("awayScore") is None and (g.get("date") or "")[:10] >= today)
    cfb_week = bpg.week_label("CFB", None, upcoming_cfb_dates[0]) if upcoming_cfb_dates else None
    for league, games, week_name in (("NFL", nfl_sched.get("games", []), nfl_week), ("CFB", cfb_games, cfb_week)):
        if not week_name:
            continue
        if any(p["league"] == league and p["week"] == week_name for p in record["parlays"]):
            continue  # this week's set is already frozen
        for p in build_for_league(league, games, ctx, today, week_name):
            if p["id"] not in existing:
                record["parlays"].append(p)
                existing.add(p["id"])
                created += 1

    # grade
    scores = {}
    for games in (nfl_sched.get("games", []), cfb_games):
        for g in games:
            if g.get("awayScore") is not None and g.get("homeScore") is not None:
                scores[(g["a"], g["b"])] = (float(g["awayScore"]), float(g["homeScore"]))
    pend_legs = [l for p in record["parlays"] if p["status"] == "pending" for l in p["legs"]
                 if l["status"] == "pending" and l["type"] != "player_prop"]
    if any((l["_away"], l["_home"]) not in scores for l in pend_legs):
        if any(p["league"] == "NFL" and p["status"] == "pending" for p in record["parlays"]):
            scores.update(tp.fetch_nfl_final_scores(2026))
        key = os.environ.get("CFBD_API_KEY", "").strip()
        if key and any(p["league"] == "CFB" and p["status"] == "pending" for p in record["parlays"]):
            scores.update(tp.fetch_cfb_final_scores(2026, key))
    graded = 0
    for p in record["parlays"]:
        if p["status"] != "pending":
            continue
        for l in p["legs"]:
            if l["status"] == "pending":
                res = grade_leg(l, scores, players)
                if res:
                    l["status"] = res
        st = parlay_status(p["legs"])
        if st != "pending":
            p["status"] = st
            p["graded_date"] = today
            graded += 1
            if st == "hit":
                d = 1.0
                for l in p["legs"]:
                    if l["status"] == "hit":
                        d *= dec(l["odds"])
                p["profit_units"] = round(d - 1, 2)
            elif st == "miss":
                p["profit_units"] = -1.0
            else:
                p["profit_units"] = 0.0

    record["version"] = VERSION
    record["updated"] = today
    with open(OUT_PATH, "w") as f:
        json.dump(record, f, indent=2)
    done = [p for p in record["parlays"] if p["status"] in ("hit", "miss")]
    hits = sum(1 for p in done if p["status"] == "hit")
    print(f"Parlay tracker: created {created} new parlays, graded {graded}. "
          f"Record so far: {hits}-{len(done) - hits} across {len(record['parlays'])} parlays.")


if __name__ == "__main__":
    main()