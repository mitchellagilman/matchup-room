#!/usr/bin/env python3
"""
Pulls per-game stat lines for every FBS AND FCS college football team's
QBs/RBs/WRs/TEs from collegefootballdata.com (CFBD) and writes
data/cfb-players.json -- keeping a rolling window of each player's most
recent 10 games, pulling from last season too if this season doesn't have
10 games yet (same idea as fetch_players_nfl.py; see that script's
docstring for the full explanation of the rolling window and why team
assignment is protected from being overwritten by historical data).

*** FCS SUPPORT -- ADDED, THEN REMOVED ***
This briefly pulled team names for both FBS and FCS so FCS players
weren't filtered out. Removed for the same reason as fetch_cfb.py: it
roughly doubled CFBD call volume against a 1,000-call/month free-tier
ceiling, for a benefit (early-season FBS-vs-FCS buy games) that stops
mattering a few weeks into the season anyway. CLASSIFICATIONS is still a
list so FCS is easy to add back later if wanted.

*** SAME HONESTY NOTE AS fetch_cfb.py ***
Could not be tested against the live CFBD API from the sandbox that wrote
this. Uses CFBD's /games/players endpoint, which -- based on what we
learned building fetch_cfb.py -- likely rejects a bare year and wants a
week too, so this goes straight to the per-week loop for both years
rather than trying a bulk call first. Test locally before trusting the
scheduled run; if it errors, it'll print a sample raw row to help debug
the field names. Pulling two full seasons roughly doubles the number of
requests versus the single-season version, and now doing that for two
classifications on top -- if this starts timing out or hitting rate
limits, that's the first thing to look at.

Sign up for a free key at https://collegefootballdata.com/key and set it
as CFBD_API_KEY.

Run: CFBD_API_KEY=xxxx python3 scripts/fetch_players_cfb.py
Writes: data/cfb-players.json
"""
import json
import os
import sys
import time
import urllib.request
import urllib.parse
from cfbd_utils import cfbd_get

YEAR = 2026
PREV_YEAR = YEAR - 1
WINDOW = 10
EXISTING_PATH = "data/cfb-players.json"
CLASSIFICATIONS = ["fbs", "fcs"]  # only used by the rare fallback path below (direct API call if data/cfb-teams.json is missing) -- restored alongside fetch_cfb.py

POSITION_HINT = {
    "passing": "QB",
    "rushing": "RB",
    "receiving": "WR",
}


def fetch_year_rows(year, api_key):
    rows = []
    for week in range(1, 16):
        try:
            batch = cfbd_get("/games/players", {"year": year, "seasonType": "regular", "week": week}, api_key)
        except Exception:
            continue  # week hasn't happened yet (or errored) -- skip it
        if batch:
            for g in batch:
                g["_year"] = year  # tag so the merge step can sort across years
            rows.extend(batch)
        time.sleep(1)  # spread out requests -- this loop alone can be 15 calls per year
    return rows


def main():
    api_key = (os.environ.get("CFBD_API_KEY") or "").strip()
    if not api_key:
        print("CFBD_API_KEY is not set -- skipping college player stats update.", file=sys.stderr)
        return

    try:
        with open(EXISTING_PATH) as f:
            players = json.load(f)
    except FileNotFoundError:
        players = {}

    # Team names come from data/cfb-teams.json (already written by
    # fetch_cfb.py, which runs earlier in the workflow) instead of calling
    # CFBD's /teams endpoint again here -- that was a fully redundant pair
    # of calls (both classifications) on every run. Falls back to a direct
    # API call only if that file is missing or empty (e.g. run standalone,
    # or fetch_cfb.py failed this run), so this script still works on its
    # own if needed.
    all_teams = set()
    try:
        with open("data/cfb-teams.json") as f:
            cfb_teams_file = json.load(f)
        all_teams = {name for name, t in cfb_teams_file.items() if t.get("league") == "CFB"}
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    if not all_teams:
        print("data/cfb-teams.json had no usable team list -- falling back to a direct CFBD /teams call.", file=sys.stderr)
        for classification in CLASSIFICATIONS:
            try:
                resp = cfbd_get("/teams", {"year": YEAR, "classification": classification}, api_key)
            except Exception as e:
                print(f"Could not reach CFBD /teams (classification={classification}) ({e}); that classification's players will be skipped.", file=sys.stderr)
                continue
            for t in resp:
                name = t.get("school")
                if name:
                    all_teams.add(name)
            time.sleep(1)

    if not all_teams:
        print("Could not fetch any team list (FBS or FCS); leaving existing file untouched.", file=sys.stderr)
        return

    all_rows = fetch_year_rows(PREV_YEAR, api_key) + fetch_year_rows(YEAR, api_key)

    if not all_rows:
        print("CFBD returned no games/players data for either season; leaving file untouched.", file=sys.stderr)
        return

    sample = all_rows[0]
    if "teams" not in sample:
        print("WARNING: /games/players response shape looks different than expected -- "
              "sample row printed below. Update the parsing loop in main() to match.", file=sys.stderr)
        print(json.dumps({k: v for k, v in sample.items() if k != "_year"}, indent=2)[:1500], file=sys.stderr)
        return

    # player name -> {pos, by_game: {(year,week): {...stats...}}}
    accum = {}

    def get_entry(name, pos, year, week, gid):
        if name not in accum:
            accum[name] = {"pos": pos, "team": None, "by_game": {}}
        gkey = (year, week, gid)
        if gkey not in accum[name]["by_game"]:
            accum[name]["by_game"][gkey] = {"year": year, "week": week, "passYds": 0, "rushYds": 0,
                                             "receptions": 0, "recYds": 0, "tds": 0}
        return accum[name]["by_game"][gkey]

    for game in all_rows:
        gid = game.get("id")
        week = game.get("week")
        year = game.get("_year")
        for team_block in game.get("teams", []):
            team = team_block.get("team") or team_block.get("school")
            if team not in all_teams:
                continue
            for category in team_block.get("categories", []):
                cat_name = (category.get("name") or "").lower()
                for stat_type in category.get("types", []):
                    stat_name = (stat_type.get("name") or "").upper()
                    for athlete in stat_type.get("athletes", []):
                        player_name = athlete.get("name")
                        if not player_name:
                            continue
                        pos = POSITION_HINT.get(cat_name, "")
                        entry = get_entry(player_name, pos, year, week, gid)
                        accum[player_name]["team"] = team  # most recently seen team wins (rows processed old->new below isn't guaranteed here, but final sort+pick-last handles it)
                        try:
                            val = float(athlete.get("stat", 0))
                        except (TypeError, ValueError):
                            continue
                        if cat_name == "passing" and stat_name == "YDS":
                            entry["passYds"] = val
                        elif cat_name == "rushing" and stat_name == "YDS":
                            entry["rushYds"] = val
                        elif cat_name == "receiving" and stat_name == "YDS":
                            entry["recYds"] = val
                        elif cat_name == "receiving" and stat_name == "REC":
                            entry["receptions"] = val
                        elif stat_name == "TD":
                            entry["tds"] = entry.get("tds", 0) + val

    updated = 0
    for name, info in accum.items():
        if not info["pos"]:
            continue  # couldn't classify into QB/RB/WR -- skip rather than guess
        sorted_games = sorted(info["by_game"].values(), key=lambda g: (g["year"], g["week"] if g["week"] is not None else -1))
        recent_games = sorted_games[-WINDOW:]

        games_out = []
        for g in recent_games:
            games_out.append({
                "date": f"{g['year']}-wk{g['week']}",
                "opp": "",
                "passYds": g["passYds"], "rushYds": g["rushYds"],
                "receptions": g["receptions"], "recYds": g["recYds"], "tds": g["tds"],
            })

        # Team: keep whatever's already there (from fetch_cfb_rosters.py's
        # current roster) if present; only use this script's own most
        # recent team as a fallback for a brand-new player.
        existing = players.get(name, {})
        team = existing.get("team") or info["team"]

        players[name] = {
            "pos": info["pos"],
            "team": team,
            "league": "CFB",
            "games": games_out,
        }
        updated += 1

    with open(EXISTING_PATH, "w") as f:
        json.dump(players, f, indent=2)
    print(f"Wrote {updated} CFB players (rolling {WINDOW}-game window, {PREV_YEAR}-{YEAR}) to {EXISTING_PATH}")


if __name__ == "__main__":
    main()
