#!/usr/bin/env python3
"""
Pulls the current week's Top 25 college football schedule and rankings
from collegefootballdata.com (CFBD) and writes data/cfb-schedule.json and
data/cfb-rankings.json.

*** SAME HONESTY NOTE AS THE OTHER CFBD SCRIPTS ***
Could not be tested against the live CFBD API from the sandbox that wrote
this. Uses /games and /rankings. Prints a warning with a sample raw row if
either response doesn't look like what's expected.

Sign up for a free key at https://collegefootballdata.com/key and set it
as CFBD_API_KEY.

Run: CFBD_API_KEY=xxxx python3 scripts/fetch_cfb_schedule.py
Writes: data/cfb-schedule.json, data/cfb-rankings.json
"""
import json
import os
import sys
import urllib.request
import urllib.parse

YEAR = 2026
API_BASE = "https://api.collegefootballdata.com"
SCHEDULE_PATH = "data/cfb-schedule.json"
RANKINGS_PATH = "data/cfb-rankings.json"


def api_get(path, params, api_key):
    url = f"{API_BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    api_key = (os.environ.get("CFBD_API_KEY") or "").strip()
    if not api_key:
        print("CFBD_API_KEY is not set -- skipping CFB schedule/rankings update.", file=sys.stderr)
        return

    try:
        all_games = api_get("/games", {"year": YEAR, "seasonType": "regular"}, api_key)
    except Exception as e:
        print(f"Could not fetch /games ({e}); leaving existing files untouched.", file=sys.stderr)
        return

    if not all_games:
        print("CFBD returned no games; leaving existing files untouched.", file=sys.stderr)
        return

    # Current week = the earliest week that ISN'T essentially finished --
    # not just "the most recently started week" (that broke too: on a day
    # between weeks, e.g. week 1 fully played but week 2 hasn't kicked off
    # yet, "most recently started" is still week 1, showing games that are
    # already over). A week counts as finished once nearly all its games
    # have a recorded result AND its last game's date has passed -- the
    # "nearly all" tolerance (not literally 100%) is what keeps a single
    # slow-to-update score from pinning a truly-over week as current forever.
    import datetime
    today = datetime.datetime.now(datetime.timezone.utc).date()
    games_by_week = {}
    for g in all_games:
        wk = g.get("week")
        if wk is None:
            continue
        games_by_week.setdefault(wk, []).append(g)

    current_week = None
    for wk in sorted(games_by_week.keys()):
        wk_games = games_by_week[wk]
        dates = []
        for g in wk_games:
            start = g.get("startDate")
            if not start:
                continue
            try:
                dates.append(datetime.datetime.fromisoformat(start.replace("Z", "+00:00")).date())
            except ValueError:
                pass
        last_date = max(dates) if dates else None
        completed = sum(1 for g in wk_games if g.get("homePoints") is not None)
        completion_ratio = (completed / len(wk_games)) if wk_games else 0
        still_relevant = (last_date is None) or (today <= last_date) or (completion_ratio < 0.8)
        if still_relevant:
            current_week = wk
            break
    if current_week is None:
        current_week = max(games_by_week.keys()) if games_by_week else 1

    try:
        rankings_resp = api_get("/rankings", {"year": YEAR, "seasonType": "regular", "week": current_week}, api_key)
    except Exception as e:
        print(f"Could not fetch /rankings ({e}); schedule will still be written, but rankings skipped.", file=sys.stderr)
        rankings_resp = []

    ap_poll = []
    if rankings_resp:
        week_block = rankings_resp[0] if isinstance(rankings_resp, list) else {}
        polls = week_block.get("polls", [])
        ap = next((p for p in polls if "AP" in (p.get("poll") or "")), None)
        if ap:
            ap_poll = ap.get("ranks", [])
        else:
            print("WARNING: couldn't find an AP poll in /rankings response -- sample printed below.", file=sys.stderr)
            print(json.dumps(rankings_resp, indent=2)[:1000], file=sys.stderr)

    ranked_teams = {r.get("school") for r in ap_poll}

    next_game = {}
    for g in sorted(all_games, key=lambda g: (g.get("week") or 0)):
        if (g.get("week") or 0) < current_week:
            continue
        home, away = g.get("homeTeam"), g.get("awayTeam")
        for team, opp, is_home in [(home, away, True), (away, home, False)]:
            if team in ranked_teams and team not in next_game:
                next_game[team] = f"{'vs' if is_home else '@'} {opp}"

    rankings_out = []
    for r in ap_poll:
        school = r.get("school")
        rankings_out.append({
            "rank": r.get("rank"),
            "team": school,
            "record": "",
            "next": next_game.get(school, ""),
        })

    with open(RANKINGS_PATH, "w") as f:
        json.dump(rankings_out, f, indent=2)

    # Every game involving at least one ranked team -- not just ranked-vs-ranked
    # (which is rare, especially in early weeks). This matches "every ranked
    # team's game this week", the same coverage the original hand-built list had.
    week_games = [g for g in all_games if g.get("week") == current_week]
    seen_pairs = set()
    schedule_out = []
    for g in week_games:
        home, away = g.get("homeTeam"), g.get("awayTeam")
        if home in ranked_teams or away in ranked_teams:
            pair = tuple(sorted([home, away]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            schedule_out.append({"a": away, "b": home, "date": (g.get("startDate") or "")[:10]})

    with open(SCHEDULE_PATH, "w") as f:
        json.dump(schedule_out, f, indent=2)

    print(f"Week {current_week}: wrote {len(rankings_out)} ranked teams to {RANKINGS_PATH} "
          f"and {len(schedule_out)} games (involving a ranked team) to {SCHEDULE_PATH}")


if __name__ == "__main__":
    main()
