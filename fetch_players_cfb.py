#!/usr/bin/env python3
"""
Pulls per-game stat lines for Power 5 college football QBs/RBs/WRs/TEs
from collegefootballdata.com (CFBD) and writes data/cfb-players.json.

*** SAME HONESTY NOTE AS fetch_cfb.py ***
Could not be tested against the live CFBD API from the sandbox that wrote
this (collegefootballdata.com isn't on that sandbox's allowed domain
list). Uses CFBD's /games/players endpoint, which -- based on what we
learned building fetch_cfb.py -- likely rejects a bare year and wants a
week too, so this goes straight to the per-week loop rather than trying
the bulk call first. Test locally before trusting the scheduled run; if
it errors, it'll print a sample raw row to help debug the field names.

Sign up for a free key at https://collegefootballdata.com/key and set it
as CFBD_API_KEY.

Run: CFBD_API_KEY=xxxx python3 scripts/fetch_players_cfb.py
Writes: data/cfb-players.json
"""
import json
import os
import sys
import urllib.request
import urllib.parse

YEAR = 2026
API_BASE = "https://api.collegefootballdata.com"
EXISTING_PATH = "data/cfb-players.json"

POWER5_CONFERENCES = {"SEC", "Big Ten", "Big 12", "ACC"}
INCLUDE_INDEPENDENTS = {"Notre Dame"}

# CFBD's /games/players groups stats by category ("passing", "rushing",
# "receiving") each with their own sub-stats (YDS, TD, REC, etc). Exact
# nesting is the part most likely to need adjusting -- see the shape
# check in main().
POSITION_HINT = {
    "passing": "QB",
    "rushing": "RB",
    "receiving": "WR",
}


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
        print("CFBD_API_KEY is not set -- skipping college player stats update.", file=sys.stderr)
        return

    try:
        with open(EXISTING_PATH) as f:
            players = json.load(f)
    except FileNotFoundError:
        players = {}

    try:
        fbs_teams = api_get("/teams/fbs", {"year": YEAR}, api_key)
    except Exception as e:
        print(f"Could not reach CFBD /teams/fbs ({e}); leaving existing file untouched.", file=sys.stderr)
        return

    power5_teams = set()
    for t in fbs_teams:
        conf = t.get("conference")
        name = t.get("school")
        if conf in POWER5_CONFERENCES or name in INCLUDE_INDEPENDENTS:
            power5_teams.add(name)

    all_rows = []
    for week in range(1, 16):
        try:
            batch = api_get("/games/players", {"year": YEAR, "seasonType": "regular", "week": week}, api_key)
        except Exception:
            continue  # week hasn't happened yet, or errored -- skip it
        if batch:
            all_rows.extend(batch)

    if not all_rows:
        print("CFBD returned no games/players data (season may not have started); leaving file untouched.", file=sys.stderr)
        return

    # Shape sanity check -- CFBD nests this as [{ id, teams: [{ team, categories: [{name, types:[{name, athletes:[{name, stat}]}]}] }] }]
    sample = all_rows[0]
    if "teams" not in sample:
        print("WARNING: /games/players response shape looks different than expected -- "
              "sample row printed below. Update the parsing loop in main() to match.", file=sys.stderr)
        print(json.dumps(sample, indent=2)[:1500], file=sys.stderr)
        return

    # player name -> {pos, team, games: {week: {passYds, rushYds, receptions, recYds, tds}}}
    accum = {}

    def get_entry(name, team, pos, week, gid):
        key = name
        if key not in accum:
            accum[key] = {"pos": pos, "team": team, "by_game": {}}
        gkey = (gid, week)
        if gkey not in accum[key]["by_game"]:
            accum[key]["by_game"][gkey] = {"week": week, "passYds": 0, "rushYds": 0,
                                            "receptions": 0, "recYds": 0, "tds": 0}
        return accum[key]["by_game"][gkey]

    for game in all_rows:
        gid = game.get("id")
        week = game.get("week")
        for team_block in game.get("teams", []):
            team = team_block.get("team") or team_block.get("school")
            if team not in power5_teams:
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
                        entry = get_entry(player_name, team, pos, week, gid)
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
        games = sorted(info["by_game"].values(), key=lambda g: g["week"])
        for g in games:
            g["date"] = f"{YEAR}-wk{g.pop('week')}"
            g["opp"] = ""
        players[name] = {
            "pos": info["pos"],
            "team": info["team"],
            "league": "CFB",
            "games": games,
        }
        updated += 1

    with open(EXISTING_PATH, "w") as f:
        json.dump(players, f, indent=2)
    print(f"Wrote {updated} CFB players to {EXISTING_PATH}")


if __name__ == "__main__":
    main()
