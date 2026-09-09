#!/usr/bin/env python3
"""
Pulls each active NFL skill-position player's last 10 games (rolling
window, dipping into last season early on) from ESPN's gamelog API and
writes data/nfl-players.json.

*** WHY ESPN INSTEAD OF nflverse ***
nflverse's player-level file (used by the previous version of this
script) stops at the 2024 season -- confirmed by fetching it live while
diagnosing this -- so no fallback logic could make it supply 2025 data
that simply isn't in the file. ESPN's gamelog endpoint does have the full
2025 season (verified live: ESPN's own "Patrick Mahomes 2025 Stats per
Game" page exists and is populated). Switching this script and
fetch_nfl_rosters.py to ESPN also means they share one athlete ID scheme,
which is what actually fixes the "DJ Moore" duplicate-entry bug -- see
fetch_nfl_rosters.py's docstring for the full story.

*** HONESTY NOTE ***
Verified the gamelog response shape live for a real athlete ID while
writing this, including that each event's stat values are positional
against a top-level "names" list (e.g. index of "receivingYards" in
"names" is where that game's receiving yards live in "stats"). NOT
verified: running this exact parsing logic against hundreds of real
athlete IDs in one batch -- the sandbox that wrote this can only reach
espn.com through a search-gated fetch tool, not directly. If a lot of
players come back with zero games logged, check this script's output for
warnings first.

Run: python3 scripts/fetch_players_nfl.py
Writes: data/nfl-players.json
"""
import json
import sys
import time
import urllib.error
import urllib.request

EXISTING_PATH = "data/nfl-players.json"
YEAR = 2026
PREV_YEAR = YEAR - 1
WINDOW = 10
SEASONS_TO_FETCH = [PREV_YEAR, YEAR]

STAT_NAME_MAP = {
    "passYds": "passingYards",
    "rushYds": "rushingYards",
    "receptions": "receptions",
    "recYds": "receivingYards",
}
TD_NAMES = ["passingTouchdowns", "rushingTouchdowns", "receivingTouchdowns"]


def api_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "matchup-room-fetcher"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def to_num(val):
    try:
        return float(str(val).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def fetch_season_games(athlete_id, season):
    url = (f"https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/"
           f"athletes/{athlete_id}/gamelog?season={season}")
    try:
        data = api_get(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []  # no games this season for this player -- normal (rookie, injured all year, etc)
        raise

    events = data.get("events", {})
    names = data.get("names", [])
    name_to_idx = {n: i for i, n in enumerate(names)}

    games = []
    for season_type in data.get("seasonTypes", []):
        for category in season_type.get("categories", []):
            for ev in category.get("events", []):
                eid = ev.get("eventId")
                stats = ev.get("stats", [])
                event_info = events.get(eid, {})
                opp = (event_info.get("opponent") or {}).get("abbreviation", "")
                week = event_info.get("week")

                def get_stat(key):
                    idx = name_to_idx.get(STAT_NAME_MAP.get(key))
                    if idx is None or idx >= len(stats):
                        return 0.0
                    return to_num(stats[idx])

                tds = 0.0
                for td_name in TD_NAMES:
                    idx = name_to_idx.get(td_name)
                    if idx is not None and idx < len(stats):
                        tds += to_num(stats[idx])

                games.append({
                    "_sortKey": (season, week or 0),
                    "date": f"{season}-wk{week}",
                    "opp": f"vs {opp}" if opp else "",
                    "passYds": get_stat("passYds"),
                    "rushYds": get_stat("rushYds"),
                    "receptions": get_stat("receptions"),
                    "recYds": get_stat("recYds"),
                    "tds": tds,
                })
    return games


def main():
    try:
        with open(EXISTING_PATH) as f:
            players = json.load(f)
    except FileNotFoundError:
        print(f"{EXISTING_PATH} doesn't exist yet -- run fetch_nfl_rosters.py first.", file=sys.stderr)
        return

    # Only fetch gamelogs for players roster-confirmed by THIS run --
    # keeps the request count proportional to the actual current league
    # size (~500 skill players) instead of every player this file has
    # ever seen, and avoids burning requests on stale/retired entries.
    targets = [(name, p) for name, p in players.items() if p.get("teamYear") == YEAR and p.get("_id")]

    updated = 0
    failed = 0
    for i, (name, p) in enumerate(targets):
        athlete_id = p["_id"]
        all_games = []
        for season in SEASONS_TO_FETCH:
            try:
                all_games.extend(fetch_season_games(athlete_id, season))
            except Exception as e:
                failed += 1
                if failed <= 5:
                    print(f"Could not fetch gamelog for {name} ({athlete_id}), season {season}: {e}", file=sys.stderr)
                continue
        if not all_games:
            continue
        all_games.sort(key=lambda g: g["_sortKey"])
        recent = all_games[-WINDOW:]
        for g in recent:
            g.pop("_sortKey", None)
        players[name]["games"] = recent
        updated += 1
        if i % 50 == 0:
            time.sleep(0.5)  # light pacing -- be a good citizen on an unofficial API

    with open(EXISTING_PATH, "w") as f:
        json.dump(players, f, indent=2)
    print(f"Wrote game logs for {updated}/{len(targets)} NFL players "
          f"(rolling {WINDOW}-game window, {PREV_YEAR}-{YEAR}); {failed} individual season fetches failed")


if __name__ == "__main__":
    main()
