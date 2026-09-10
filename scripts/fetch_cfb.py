#!/usr/bin/env python3
"""
Pulls current-season stats for every FBS AND FCS college football team --
offense AND defense -- from collegefootballdata.com (CFBD) and writes
data/cfb-teams.json.

*** IMPORTANT HONESTY NOTE ***
Unlike scripts/fetch_nfl.py (which was tested live against real nflverse
files while writing it), this script could NOT be tested against the live
CFBD API from the environment that built it -- that sandbox's network
policy only allows a fixed list of domains, and collegefootballdata.com
isn't on it. The endpoint shapes below (/games and /games/teams) reflect
CFBD's documented API as of when this was written, but field names in
particular (homeTeam vs home_team, "school" vs "team", etc.) are the part
most likely to have drifted or been mis-remembered. TEST THIS LOCALLY with
your own API key before trusting the GitHub Action to run it unattended --
see the try/except block in main() for what it prints if something's off,
and check https://api.collegefootballdata.com/api-docs if it errors.

The approach itself (independent of exact field names) is solid and is the
same trick used in fetch_nfl.py: CFBD's stats endpoints are offense-only,
so for team X's defense in a given game, we look up the OTHER team's
offensive output in that same game and count it as what X allowed.

*** FCS SUPPORT -- ALSO UNVERIFIED LIVE ***
CFBD's documentation confirms /teams, /games, and /games/teams all accept
a `classification` param with values "fbs"/"fcs" (confirmed via the
API's published parameter docs, not a live call). This script now fetches
both classifications and merges them into one team list with a `division`
field. If classification=fcs comes back empty or errors for any of these
three endpoints, that's the first thing to check -- the script will print
which classification failed and continue with whichever one worked,
rather than failing the whole run.

Team names are matched between /teams and /games/teams by CFBD's own
"school" field -- keep it that way rather than inventing an alternate
spelling (e.g. adding a disambiguating suffix) anywhere in this project.
A prior version of this project's seed data used "Miami (FL)" to
disambiguate from Miami (OH), which doesn't match CFBD's real name
("Miami") and caused two permanently-diverging entries for the same team
-- see the fix in index.html's CFB_SEED for the full story. The lesson:
always use the exact string CFBD itself returns, never an invented
disambiguator, no matter how reasonable it seems.

Sign up for a free key at https://collegefootballdata.com and set it as
CFBD_API_KEY.

Run: CFBD_API_KEY=xxxx python3 scripts/fetch_cfb.py
Writes: data/cfb-teams.json
"""
import json
import os
import sys
import urllib.request
import urllib.parse

YEAR = 2026
API_BASE = "https://api.collegefootballdata.com"
EXISTING_PATH = "data/cfb-teams.json"
CLASSIFICATIONS = ["fbs", "fcs"]

# The two offensive categories CFBD's games/teams stats use that we need.
# CFBD's documented category strings -- verify against a live response if
# this script comes back empty (print(stats_row) in the loop below to check).
PASS_YARDS_KEYS = ["netPassingYards", "passingYards"]
RUSH_YARDS_KEYS = ["rushingYards"]


def api_get(path, params, api_key):
    url = f"{API_BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def first_present(d, keys, default=0):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            try:
                return float(d[k])
            except (TypeError, ValueError):
                continue
    return default


def get_team_name(team_obj):
    # CFBD has used both "school" and "team" for this field across
    # endpoint versions -- try both.
    return team_obj.get("school") or team_obj.get("team")


def get_stats_dict(team_obj):
    """Turn CFBD's [{category, stat}, ...] list into a flat {category: value} dict."""
    out = {}
    for row in team_obj.get("stats", []) or []:
        cat = row.get("category")
        val = row.get("stat")
        if cat is not None:
            out[cat] = val
    return out


def fetch_games_teams_for(classification, api_key):
    """Bulk-fetch /games/teams for one classification, falling back to
    per-week requests if the bulk call rejects a bare year (confirmed live
    that this happens for at least one classification -- see the
    fallback comment below)."""
    try:
        return api_get("/games/teams", {"year": YEAR, "seasonType": "regular", "classification": classification}, api_key)
    except Exception as e:
        # /games/teams appears to reject a bare year (400) and want a week too --
        # confirmed against the live API after this script was first written.
        # Fall back to pulling it one week at a time and merging the results.
        print(f"Bulk /games/teams ({classification}) by year failed ({e}); falling back to per-week requests...", file=sys.stderr)
        out = []
        for week in range(1, 16):
            try:
                batch = api_get("/games/teams", {"year": YEAR, "seasonType": "regular", "week": week, "classification": classification}, api_key)
            except Exception:
                continue  # that week likely hasn't happened yet, or errored -- skip it
            if batch:
                out.extend(batch)
        return out


def main():
    api_key = (os.environ.get("CFBD_API_KEY") or "").strip()
    if not api_key:
        print("CFBD_API_KEY is not set -- skipping college stats update.", file=sys.stderr)
        return

    try:
        with open(EXISTING_PATH) as f:
            teams = json.load(f)
    except FileNotFoundError:
        teams = {}

    # Team -> (conference, division) for every FBS + FCS team.
    all_team_meta = {}
    for classification in CLASSIFICATIONS:
        try:
            resp = api_get("/teams", {"year": YEAR, "classification": classification}, api_key)
        except Exception as e:
            print(f"Could not reach CFBD /teams (classification={classification}) ({e}); skipping this classification for the team list.", file=sys.stderr)
            continue
        for t in resp:
            name = t.get("school")
            if name:
                all_team_meta[name] = (t.get("conference") or "Independent", classification)

    if not all_team_meta:
        print("Could not fetch any team list (FBS or FCS); leaving existing file untouched.", file=sys.stderr)
        return

    try:
        games = api_get("/games", {"year": YEAR, "seasonType": "regular"}, api_key)
    except Exception as e:
        print(f"Could not fetch /games ({e}); leaving existing file untouched.", file=sys.stderr)
        return

    games_teams = []
    for classification in CLASSIFICATIONS:
        batch = fetch_games_teams_for(classification, api_key)
        if batch:
            games_teams.extend(batch)
        else:
            print(f"No /games/teams data came back for classification={classification} -- that classification's teams will be skipped this run.", file=sys.stderr)

    if not games_teams:
        print("CFBD returned no games/teams data (season may not have started); leaving file untouched.", file=sys.stderr)
        return
    # Sanity check on the shape we got, so a silent field-name mismatch
    # doesn't quietly write all-zero stats.
    sample_team = (games_teams[0].get("teams") or [{}])[0]
    if not get_stats_dict(sample_team):
        print("WARNING: couldn't find a 'stats' list on the sample game/team row -- "
              "the API shape may have changed. Sample row printed below; "
              "update get_stats_dict()/get_team_name() to match.", file=sys.stderr)
        print(json.dumps(sample_team, indent=2)[:1000], file=sys.stderr)
        return

    # game id -> team name -> offensive stats dict, for the opponent lookup.
    offense_by_game_team = {}
    for g in games_teams:
        gid = g.get("id")
        entry = {}
        for team_obj in g.get("teams", []):
            name = get_team_name(team_obj)
            if name:
                entry[name] = get_stats_dict(team_obj)
        offense_by_game_team[gid] = entry

    # team -> {for: [...], against: [...]} points, from /games directly.
    points_by_team = {}
    for g in games:
        home, away = g.get("homeTeam"), g.get("awayTeam")
        hp, ap = g.get("homePoints"), g.get("awayPoints")
        if hp is None or ap is None:
            continue  # not played yet
        points_by_team.setdefault(home, []).append({"for": hp, "against": ap})
        points_by_team.setdefault(away, []).append({"for": ap, "against": hp})

    per_team_games = {}  # team -> list of {passOff, rushOff, passDef, rushDef}
    for gid, teams_in_game in offense_by_game_team.items():
        names = list(teams_in_game.keys())
        if len(names) != 2:
            continue
        a, b = names
        for me, opp in [(a, b), (b, a)]:
            my_stats, opp_stats = teams_in_game[me], teams_in_game[opp]
            per_team_games.setdefault(me, []).append({
                "passOff": first_present(my_stats, PASS_YARDS_KEYS),
                "rushOff": first_present(my_stats, RUSH_YARDS_KEYS),
                "passDef": first_present(opp_stats, PASS_YARDS_KEYS),
                "rushDef": first_present(opp_stats, RUSH_YARDS_KEYS),
            })

    updated = 0
    fbs_updated = 0
    fcs_updated = 0
    for team, (conf, division) in all_team_meta.items():
        games_list = per_team_games.get(team)
        if not games_list:
            continue  # team hasn't played yet this season (or its games/teams data didn't come through)
        n = len(games_list)
        pts = points_by_team.get(team, [])
        np_ = len(pts) or 1
        wins = sum(1 for p in pts if p["for"] > p["against"])
        losses = sum(1 for p in pts if p["for"] < p["against"])
        ties = sum(1 for p in pts if p["for"] == p["against"])
        record = f"{wins}-{losses}" + (f"-{ties}" if ties else "")
        existing = teams.get(team, {})
        teams[team] = {
            "league": "CFB",
            "conf": conf,
            "division": division,  # "fbs" or "fcs" -- lets the UI show a pill if it wants to distinguish
            "record": record if pts else existing.get("record", ""),
            "ppg": round(sum(p["for"] for p in pts) / np_, 1) if pts else existing.get("ppg", 0),
            "pa": round(sum(p["against"] for p in pts) / np_, 1) if pts else existing.get("pa", 0),
            "passOff": round(sum(g["passOff"] for g in games_list) / n, 1),
            "rushOff": round(sum(g["rushOff"] for g in games_list) / n, 1),
            "passDef": round(sum(g["passDef"] for g in games_list) / n, 1),
            "rushDef": round(sum(g["rushDef"] for g in games_list) / n, 1),
            "to": existing.get("to", 0),  # turnover margin needs a separate CFBD endpoint; left as-is for now
            "ats": existing.get("ats", ""),
            "wk1": True,
        }
        updated += 1
        if division == "fbs":
            fbs_updated += 1
        else:
            fcs_updated += 1

    with open(EXISTING_PATH, "w") as f:
        json.dump(teams, f, indent=2)
    print(f"Updated {updated} of {len(all_team_meta)} CFB teams in {EXISTING_PATH} "
          f"({fbs_updated} FBS, {fcs_updated} FCS)")


if __name__ == "__main__":
    main()
