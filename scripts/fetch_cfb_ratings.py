#!/usr/bin/env python3
"""
Pulls CollegeFootballData's SP+ ratings (opponent-adjusted team strength,
unlike raw box-score yards/points which don't account for who a team has
actually played) and merges an "spPlus" field onto each team already in
data/cfb-teams.json. index.html's projection model blends this in when
present -- see computeProjection() in index.html.

*** SAME HONESTY NOTE AS THE OTHER CFBD SCRIPTS ***
Could not be tested against the live CFBD API from the sandbox that wrote
this. Uses /ratings/sp?year=YEAR. Field names for the overall rating in
particular are the part most likely to need adjusting -- prints a sample
raw row if none of the expected keys are found, rather than guessing.

IMPORTANT: this must run AFTER fetch_cfb.py in the workflow, not before --
fetch_cfb.py fully overwrites each team's object, which would wipe out
the spPlus field if this ran first.

Sign up for a free key at https://collegefootballdata.com/key and set it
as CFBD_API_KEY.

Run: CFBD_API_KEY=xxxx python3 scripts/fetch_cfb_ratings.py
Writes: data/cfb-teams.json (adds/updates the spPlus field only)
"""
import json
import os
import sys
import urllib.request
import urllib.parse

YEAR = 2026
API_BASE = "https://api.collegefootballdata.com"
EXISTING_PATH = "data/cfb-teams.json"

RATING_KEYS = ["rating", "spPlus", "sp_plus"]


def api_get(path, params, api_key):
    url = f"{API_BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def first_present(d, keys):
    for k in keys:
        if d.get(k) is not None:
            return d[k]
    return None


def main():
    api_key = (os.environ.get("CFBD_API_KEY") or "").strip()
    if not api_key:
        print("CFBD_API_KEY is not set -- skipping SP+ ratings update.", file=sys.stderr)
        return

    try:
        with open(EXISTING_PATH) as f:
            teams = json.load(f)
    except FileNotFoundError:
        print(f"{EXISTING_PATH} doesn't exist yet -- run fetch_cfb.py first.", file=sys.stderr)
        return

    try:
        ratings = api_get("/ratings/sp", {"year": YEAR}, api_key)
    except Exception as e:
        print(f"Could not fetch /ratings/sp ({e}); leaving existing file untouched.", file=sys.stderr)
        return

    if not ratings:
        print("CFBD returned no SP+ ratings (may not be published yet this early in the season); leaving file untouched.", file=sys.stderr)
        return

    sample = ratings[0]
    if first_present(sample, RATING_KEYS) is None:
        print("WARNING: couldn't find a rating value in /ratings/sp response -- "
              "sample row printed below. Update RATING_KEYS in this script to match.", file=sys.stderr)
        print(json.dumps(sample, indent=2)[:800], file=sys.stderr)
        return

    updated = 0
    for row in ratings:
        team = row.get("team")
        rating = first_present(row, RATING_KEYS)
        if not team or team not in teams or rating is None:
            continue
        try:
            teams[team]["spPlus"] = round(float(rating), 1)
            updated += 1
        except (TypeError, ValueError):
            continue

    with open(EXISTING_PATH, "w") as f:
        json.dump(teams, f, indent=2)
    print(f"Added SP+ ratings to {updated} teams in {EXISTING_PATH}")


if __name__ == "__main__":
    main()
