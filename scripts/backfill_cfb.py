#!/usr/bin/env python3
"""
One-time (safe to leave in the workflow) CFB backfill: logs and grades the
team-bet picks the model WOULD have made for CFB games that were never
tracked because CFB data was stale (the CFBD key was returning 401, so
fetch_cfb_schedule.py kept "leaving existing files untouched").

HOW IT WORKS
- Pulls the real market lines for each missing week from CFBD's /lines
  endpoint (one call per week; DraftKings preferred, else the first book
  with a line) plus that week's AP poll from /rankings (one call per week)
  so the same "game involves a ranked team" scope the live tracker uses
  applies here.
- For each game it rebuilds each team's season stats AS OF the game date
  from the team game logs (only games played BEFORE that date) and runs
  the exact same compute_team_bets() the live tracker uses, then grades
  against the real final score.
- Every backfilled pick is flagged "backfilled": true.
- Idempotent: a pick whose id already exists is skipped, so re-running
  adds nothing twice.

HONEST LIMITS (also shown in the log)
- ppg/pa/games/rest are rebuilt as-of the game date, but SP+ ratings,
  turnover margin and yardage stats are only available as of NOW, so a
  few inputs carry slight look-ahead. Results are somewhat optimistic
  versus picks made live.
- /lines returns the latest (closing-ish) line, which is sharper than the
  line you would have seen early in the week.

Run: python3 scripts/backfill_cfb.py
Env: CFBD_API_KEY (required), BACKFILL_FROM (default 2026-09-20),
     BACKFILL_YEAR (default 2026)
"""
import datetime
import os
import re
import sys

import track_predictions as tp
from cfbd_utils import cfbd_get

FROM_DATE = os.environ.get("BACKFILL_FROM", "2026-09-20")
YEAR = int(os.environ.get("BACKFILL_YEAR", "2026"))
PREFERRED_BOOKS = ("DraftKings", "Bovada", "ESPN Bet", "consensus")
SPREAD_RE = re.compile(r"^(.*?)\s*([+-]?\d+(?:\.\d+)?)\s*$")


def week_of(date_str):
    """CFB regular-season week number from a game date (week 1 ~ Aug 29-Sep 6)."""
    start = datetime.date(YEAR, 8, 29)
    d = datetime.date.fromisoformat(date_str)
    return max(1, (d - start).days // 7 + 1)


def pick_line(game):
    """Returns (spread_for_home, total) or (None, None)."""
    lines = [l for l in (game.get("lines") or []) if l.get("spread") is not None or l.get("formattedSpread")]
    if not lines:
        return None, None
    chosen = None
    for name in PREFERRED_BOOKS:
        chosen = next((l for l in lines if (l.get("provider") or "").lower() == name.lower()), None)
        if chosen:
            break
    chosen = chosen or lines[0]
    home, away = game.get("homeTeam"), game.get("awayTeam")
    spread_home = None
    fs = chosen.get("formattedSpread")
    if fs:
        m = SPREAD_RE.match(fs.strip())
        if m:
            team, val = m.group(1).strip(), float(m.group(2))
            if tp.team_names_match(team, home):
                spread_home = val
            elif tp.team_names_match(team, away):
                spread_home = -val
    if spread_home is None and chosen.get("spread") is not None:
        spread_home = float(chosen["spread"])  # CFBD convention: home team's spread (negative = home favored)
    total = chosen.get("overUnder")
    return spread_home, (float(total) if total is not None else None)


def teams_as_of(teams, names, date_str):
    """Shallow-copies the given teams with stats rebuilt from games before date_str."""
    out = dict(teams)
    for n in names:
        t = teams.get(n)
        if not t:
            continue
        prior = [g for g in (t.get("games") or []) if g.get("date") and g["date"] < date_str]
        c = dict(t)
        c["games"] = prior
        if prior:
            c["ppg"] = sum(g.get("teamScore", 0) for g in prior) / len(prior)
            c["pa"] = sum(g.get("oppScore", 0) for g in prior) / len(prior)
        # Venue splits can't be rebuilt from the game log (no home/away flag),
        # so fall back to the season-level blend.
        c["homeGames"] = 0
        c["awayGames"] = 0
        out[n] = c
    return out


def main():
    key = os.environ.get("CFBD_API_KEY")
    if not key:
        print("CFBD_API_KEY not set; skipping CFB backfill.")
        return
    today = datetime.date.today().isoformat()
    teams = {}
    teams.update(tp.load_json("data/nfl-teams.json", {}))
    teams.update(tp.load_json("data/cfb-teams.json", {}))
    calibration = tp.load_json("data/calibration.json", {})
    record = tp.load_json(tp.TRACK_PATH, {"picks": []})
    existing = {p["id"] for p in record["picks"]}

    w_start, w_end = week_of(FROM_DATE), week_of(today)
    added = {"hit": 0, "miss": 0, "push": 0}
    games_seen = games_used = 0
    for wk in range(w_start, w_end + 1):
        try:
            lines = cfbd_get("/lines", {"year": YEAR, "week": wk, "seasonType": "regular"}, key)
        except Exception as e:
            print(f"Week {wk}: could not fetch /lines ({e}); skipping this week.", file=sys.stderr)
            continue
        ranked = set()
        try:
            polls = cfbd_get("/rankings", {"year": YEAR, "week": wk, "seasonType": "regular"}, key)
            for entry in polls:
                for poll in entry.get("polls", []):
                    if "AP" in (poll.get("poll") or ""):
                        ranked.update(r.get("school") for r in poll.get("ranks", []))
        except Exception as e:
            print(f"Week {wk}: could not fetch rankings ({e}); falling back to data/cfb-rankings.json", file=sys.stderr)
            for r in tp.load_json("data/cfb-rankings.json", []):
                ranked.add(r.get("team"))

        for g in lines:
            date = (g.get("startDate") or "")[:10]
            if not date or date < FROM_DATE or date >= today:
                continue
            away, home = g.get("awayTeam"), g.get("homeTeam")
            if g.get("homeScore") is None or g.get("awayScore") is None:
                continue
            games_seen += 1
            if away not in ranked and home not in ranked:
                continue
            spread_home, total = pick_line(g)
            if spread_home is None and total is None:
                continue
            if away not in teams or home not in teams:
                continue
            a_spread = -spread_home if spread_home is not None else None
            market = {
                "aTeam": away, "bTeam": home, "date": date,
                "aSpread": a_spread, "bSpread": spread_home,
                "aSpreadOdds": -110, "bSpreadOdds": -110,
                "total": total, "overOdds": -110, "underOdds": -110,
            }
            asof = teams_as_of(teams, (away, home), date)
            if len(asof[away]["games"]) < 1 or len(asof[home]["games"]) < 1:
                continue
            game = {"a": away, "b": home, "date": date}
            cands = tp.compute_team_bets([game], asof, [market], "CFB", {}, {}, {})
            final = {(away, home): (float(g["awayScore"]), float(g["homeScore"]))}
            made = False
            for p in cands:
                pid = f"CFB|CFB-{date}|{p['matchup']}|{p['type']}"
                if pid in existing:
                    continue
                tier_label = tp.confidence_tier(p["edge"], p.get("used_sp", False), "CFB", calibration)
                pick = {
                    "id": pid, "league": "CFB", "week": f"CFB-{date}", "matchup": p["matchup"],
                    "type": p["type"], "label": p["label"], "edge": round(p["edge"], 1),
                    "date_logged": date, "status": "pending", "graded_date": None,
                    "_away": away, "_home": home,
                    "line": p.get("line"), "favored_team": p.get("favored_team"), "direction": p.get("direction"),
                    "tier": tier_label, "strength": tp.simplify_tier(tier_label),
                    "backfilled": True,
                }
                result = tp.grade_team_pick(pick, final)
                if result is None:
                    continue
                pick["status"] = result
                pick["graded_date"] = today
                record["picks"].append(pick)
                existing.add(pid)
                added[result] += 1
                made = True
            if made:
                games_used += 1

    total_added = sum(added.values())
    if total_added:
        import json
        with open(tp.TRACK_PATH, "w") as f:
            json.dump(record, f, indent=2)
    graded = added["hit"] + added["miss"]
    pct = f"{added['hit'] / graded * 100:.0f}%" if graded else "n/a"
    print(f"CFB backfill: looked at {games_seen} finished games from {FROM_DATE}, backfilled {total_added} picks "
          f"from {games_used} games -> {added['hit']} hit, {added['miss']} miss, {added['push']} push ({pct}). "
          f"Note: SP+/turnover/yardage inputs are current-as-of-now, so this is somewhat optimistic.")


if __name__ == "__main__":
    main()