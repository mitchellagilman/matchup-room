#!/usr/bin/env python3
"""
Pulls CollegeFootballData's expanded SRS (Simple Rating System) ratings --
which, unlike SP+, actually cover FCS teams -- and merges an "srs" field
onto each team already in data/cfb-teams.json. index.html's
computeProjection() uses this as a fallback opponent-adjusted signal when
SP+ isn't available for one or both teams (which is always true for any
FCS team).

*** WHY THIS EXISTS ***
Confirmed live against a real matchup: Indiana (ranked, spPlus 24.1) vs.
Howard (FCS, no spPlus, and no market line loaded for this specific game
either) fell through BOTH of computeProjection's existing safeguards --
the SP+ blend (needs spPlus on both teams) and the market-anchor blend
(needs real odds data, which isn't available for every FCS buy game) --
landing on raw, unprotected box-score-only math for a game that should
have been a blowout. SRS closes that gap: CFBD's own docs confirm the
/ratings/srs/expanded endpoint explicitly covers FCS teams, verified via
their published API reference (real documented response shape, not a
live call from this sandbox -- same honesty caveat as the other CFBD
scripts here).

SRS is a simpler methodology than SP+ (schedule-adjusted scoring margin,
not the more sophisticated efficiency-based SP+), so index.html trusts it
somewhat less than SP+ when both are available, but far more than raw
box-score-only, which has no opponent-adjustment at all.

IMPORTANT: like fetch_cfb_ratings.py, this must run AFTER fetch_cfb.py in
the workflow -- fetch_cfb.py fully overwrites each team's object, which
would wipe out the srs field if this ran first.

Sign up for a free key at https://collegefootballdata.com/key and set it
as CFBD_API_KEY.

Run: CFBD_API_KEY=xxxx python3 scripts/fetch_cfb_srs.py
Writes: data/cfb-teams.json (adds/updates the srs field only)
"""
import json
import os
import sys
from cfbd_utils import cfbd_get

YEAR = 2026
EXISTING_PATH = "data/cfb-teams.json"


def main():
    api_key = (os.environ.get("CFBD_API_KEY") or "").strip()
    if not api_key:
        print("CFBD_API_KEY is not set -- skipping SRS ratings update.", file=sys.stderr)
        return

    try:
        with open(EXISTING_PATH) as f:
            teams = json.load(f)
    except FileNotFoundError:
        print(f"{EXISTING_PATH} doesn't exist yet -- run fetch_cfb.py first.", file=sys.stderr)
        return

    try:
        ratings = cfbd_get("/ratings/srs/expanded", {"year": YEAR}, api_key)
    except Exception as e:
        print(f"Could not fetch /ratings/srs/expanded ({e}); leaving existing file untouched.", file=sys.stderr)
        return

    if not ratings:
        print("CFBD returned no SRS ratings (may not be published yet this early in the season); leaving file untouched.", file=sys.stderr)
        return

    sample = ratings[0]
    if "rating" not in sample or "team" not in sample:
        print("WARNING: /ratings/srs/expanded response shape looks different than expected -- "
              "sample row printed below.", file=sys.stderr)
        print(json.dumps(sample, indent=2)[:800], file=sys.stderr)
        return

    updated = 0
    fbs_updated = 0
    fcs_updated = 0
    for row in ratings:
        team = row.get("team")
        rating = row.get("rating")
        if not team or team not in teams or rating is None:
            continue
        try:
            teams[team]["srs"] = round(float(rating), 1)
            updated += 1
            if teams[team].get("division") == "fcs":
                fcs_updated += 1
            else:
                fbs_updated += 1
        except (TypeError, ValueError):
            continue

    with open(EXISTING_PATH, "w") as f:
        json.dump(teams, f, indent=2)
    print(f"Added SRS ratings to {updated} teams in {EXISTING_PATH} ({fbs_updated} FBS, {fcs_updated} FCS)")


if __name__ == "__main__":
    main()
