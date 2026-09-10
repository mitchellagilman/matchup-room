#!/usr/bin/env python3
"""
Pulls the full current-season roster (skill positions, every FBS AND FCS
team, not just players who've recorded a stat yet) from
collegefootballdata.com (CFBD) and writes data/cfb-players.json.

*** TEAM FILTER: WHY IT EXISTS AND WHAT IT DOES NOW ***
/roster has no classification param to filter server-side, and this
script used to call it with no filtering at all -- so it kept pulling
literally every team's players regardless of what fetch_cfb.py and
fetch_players_cfb.py were doing with FBS/FCS. Now filters client-side
against whatever team names are already sitting in data/cfb-teams.json
(written by fetch_cfb.py, which runs earlier in the workflow) -- costs
zero extra API calls, since it's just reading a file already on disk.
Since fetch_cfb.py now writes BOTH FBS and FCS teams (see its docstring),
this naturally includes FCS players again too without needing its own
FBS/FCS distinction -- it just trusts "is this a team we know about at
all," which is exactly what it needs.

*** SAME HONESTY NOTE AS THE OTHER CFBD SCRIPTS ***
Could not be tested against the live CFBD API from the sandbox that wrote
this. Uses /roster?year=YEAR. Field names for a player's name in
particular ("firstName"/"lastName" vs "first_name"/"last_name") are the
part most likely to need adjusting -- this script tries several
candidates and prints a sample raw row if none of them work, rather than
silently writing garbage.

This only sets team/position (with an empty game log) for players who
don't already have real logged games from fetch_players_cfb.py -- that
script's team assignment (from an actual game) takes precedence once it
exists; this just fills in everyone else so the full roster is browsable
even before a player has touched the ball.

Sign up for a free key at https://collegefootballdata.com/key and set it
as CFBD_API_KEY.

Run: CFBD_API_KEY=xxxx python3 scripts/fetch_cfb_rosters.py
Writes: data/cfb-players.json
"""
import json
import os
import sys
import urllib.request
import urllib.parse
from cfbd_utils import cfbd_get

YEAR = 2026
EXISTING_PATH = "data/cfb-players.json"
TEAMS_PATH = "data/cfb-teams.json"
SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}

FIRST_NAME_KEYS = ["firstName", "first_name"]
LAST_NAME_KEYS = ["lastName", "last_name"]
POSITION_KEYS = ["position"]
TEAM_KEYS = ["team"]


def first_present(d, keys):
    for k in keys:
        if d.get(k):
            return d[k]
    return None


def main():
    api_key = (os.environ.get("CFBD_API_KEY") or "").strip()
    if not api_key:
        print("CFBD_API_KEY is not set -- skipping college roster update.", file=sys.stderr)
        return

    try:
        with open(EXISTING_PATH) as f:
            players = json.load(f)
    except FileNotFoundError:
        players = {}

    known_teams = set()
    try:
        with open(TEAMS_PATH) as f:
            teams_file = json.load(f)
        known_teams = {name for name, t in teams_file.items() if t.get("league") == "CFB"}
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    if not known_teams:
        print(f"{TEAMS_PATH} had no usable team list -- run fetch_cfb.py first, or this run can't filter out garbage/unrecognized team names.", file=sys.stderr)
        return

    try:
        roster = cfbd_get("/roster", {"year": YEAR}, api_key, timeout=60)
    except Exception as e:
        print(f"Could not fetch /roster ({e}); leaving existing file untouched.", file=sys.stderr)
        return

    if not roster:
        print("CFBD returned no roster data; leaving existing file untouched.", file=sys.stderr)
        return

    sample = roster[0]
    if not first_present(sample, POSITION_KEYS) or not first_present(sample, TEAM_KEYS):
        print("WARNING: /roster response shape looks different than expected -- "
              "sample row printed below. Update the *_KEYS lists in this script to match.", file=sys.stderr)
        print(json.dumps(sample, indent=2)[:1000], file=sys.stderr)
        return

    updated = 0
    skipped_unknown_team = 0
    for row in roster:
        pos = first_present(row, POSITION_KEYS)
        if pos not in SKILL_POSITIONS:
            continue
        team = first_present(row, TEAM_KEYS)
        if team not in known_teams:
            skipped_unknown_team += 1
            continue
        first = first_present(row, FIRST_NAME_KEYS) or ""
        last = first_present(row, LAST_NAME_KEYS) or ""
        name = (first + " " + last).strip()
        if not name:
            continue
        existing = players.get(name)
        if existing and existing.get("games"):
            continue  # already has real logged games -- don't overwrite
        players[name] = {
            "pos": pos,
            "team": team,
            "league": "CFB",
            "games": [],
        }
        updated += 1

    with open(EXISTING_PATH, "w") as f:
        json.dump(players, f, indent=2)
    print(f"Wrote/updated {updated} CFB players (FBS+FCS, matched against known teams -- skipped {skipped_unknown_team} rows with an unrecognized team name) to {EXISTING_PATH}")


if __name__ == "__main__":
    main()
