#!/usr/bin/env python3
"""
Pulls the full current-season FBS roster (skill positions, every team, not
just players who've recorded a stat yet) from collegefootballdata.com
(CFBD) and writes data/cfb-players.json.

*** SAME HONESTY NOTE AS THE OTHER CFBD SCRIPTS ***
Could not be tested against the live CFBD API from the sandbox that wrote
this. Uses /roster?year=YEAR (documented as returning every FBS team's
roster in one call). Field names for a player's name in particular
("firstName"/"lastName" vs "first_name"/"last_name") are the part most
likely to need adjusting -- this script tries several candidates and
prints a sample raw row if none of them work, rather than silently
writing garbage.

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

YEAR = 2026
API_BASE = "https://api.collegefootballdata.com"
EXISTING_PATH = "data/cfb-players.json"
SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}

FIRST_NAME_KEYS = ["firstName", "first_name"]
LAST_NAME_KEYS = ["lastName", "last_name"]
POSITION_KEYS = ["position"]
TEAM_KEYS = ["team"]


def api_get(path, params, api_key):
    url = f"{API_BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


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

    try:
        roster = api_get("/roster", {"year": YEAR}, api_key)
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
    for row in roster:
        pos = first_present(row, POSITION_KEYS)
        if pos not in SKILL_POSITIONS:
            continue
        first = first_present(row, FIRST_NAME_KEYS) or ""
        last = first_present(row, LAST_NAME_KEYS) or ""
        name = (first + " " + last).strip()
        if not name:
            continue
        existing = players.get(name)
        if existing and existing.get("games"):
            continue  # already has real logged games -- don't overwrite
        team = first_present(row, TEAM_KEYS)
        players[name] = {
            "pos": pos,
            "team": team,
            "league": "CFB",
            "games": [],
        }
        updated += 1

    with open(EXISTING_PATH, "w") as f:
        json.dump(players, f, indent=2)
    print(f"Wrote/updated {updated} CFB players (current roster) to {EXISTING_PATH}")


if __name__ == "__main__":
    main()
