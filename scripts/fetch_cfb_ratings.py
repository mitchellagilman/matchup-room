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

*** FCS TEAMS DON'T GET spPlus, AND THAT'S EXPECTED ***
SP+ is an FBS-only rating (confirmed via CFBD's own published rankings,
which are explicitly headlined "all N FBS teams" with no FCS equivalent
metric). This script needs no FCS-specific change: it already skips any
team not present in the /ratings/sp response, so FCS teams simply never
get an spPlus field. index.html's computeProjection() already handles a
missing spPlus by falling back to box-score-only projection -- the same
path any early-season FBS team without a published rating yet already
takes.

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
from cfbd_utils import cfbd_get

YEAR = 2026
EXISTING_PATH = "data/cfb-teams.json"

RATING_KEYS = ["rating", "spPlus", "sp_plus"]


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
        ratings = cfbd_get("/ratings/sp", {"year": YEAR}, api_key)
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
