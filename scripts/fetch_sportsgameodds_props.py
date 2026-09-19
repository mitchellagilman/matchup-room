#!/usr/bin/env python3
"""
Pulls REAL sportsbook player-prop lines (passing/rushing/receiving yards)
from the SportsGameOdds API and writes data/player-props-odds.json --
same output format and destination as fetch_player_props_odds.py, so
track_predictions.py and index.html need no changes to consume this.

*** WHY A SECOND PROVIDER ***
Confirmed live: The Odds API's player-prop endpoint (fetch_player_props_odds.py)
returns HTTP 401 Unauthorized on every single event call, consistently,
while the SAME key works fine for that provider's basic game odds. That
points to a plan-tier gate on this specific feature, not a bug on this
end -- the account's plan may simply not include player props. This
script targets SportsGameOdds instead, whose free tier explicitly lists
Player Props as included (confirmed via a screenshot of their pricing
page), rather than continuing to guess at the first provider's access
level.

*** CONFIDENCE LEVEL ON THIS INTEGRATION ***
Higher than the other two fixes made this session (CFBD turnover margin,
The Odds API player props) going in -- SportsGameOdds publishes an
AI-specific integration guide (sportsgameodds.com/docs/info/ai-vibe-coding)
with exact field names, an OpenAPI spec, and worked examples, which this
script was built directly against rather than reverse-engineered from
scattered docs. Still unverified against a real live response in this
environment though, so the same diagnostic-logging safety net applies:
if the real shape doesn't match, the next workflow log will show exactly
why instead of silently producing nothing.

*** BUDGET ***
Free tier: 2,500 "objects" per month, 10 requests/minute. Objects appear
to be billed per EVENT returned (each event's odds/players/teams are
fields on that one object, not separately billed) based on how the API
is structured, but this is the one part of this integration not
confirmed against SportsGameOdds' own docs directly -- if usage burns
through the free tier much faster than expected, that assumption is the
first thing to revisit. The same RE_FETCH_DAYS + MAX_EVENTS_PER_RUN
protections used for The Odds API integration apply here too, sized
conservatively for this same reason.

Run: SPORTSGAMEODDS_API_KEY=xxxx python3 scripts/fetch_sportsgameodds_props.py
Writes: data/player-props-odds.json (shared with fetch_player_props_odds.py)
Also writes: data/player-props-fetch-log.json (shared -- a game fetched by
either script won't be needlessly re-fetched by the other)
"""
import datetime
import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

API_BASE = "https://api.sportsgameodds.com/v2/events"
OUT_PATH = "data/player-props-odds.json"
FETCH_LOG_PATH = "data/player-props-fetch-log.json"
LEAGUE_IDS = "NFL,NCAAF"  # confirmed both included on the free tier via pricing page screenshot
TARGET_STATS = {"passing_yards": "passYds", "rushing_yards": "rushYds", "receiving_yards": "recYds"}
MAX_EVENTS_PER_RUN = 40  # conservative first-run cap given the unconfirmed "objects" billing assumption above -- easy to raise once real usage is observed via the /account/usage endpoint
RE_FETCH_DAYS = 3  # shared fetch log with fetch_player_props_odds.py -- see that script's comment for the reasoning


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def api_get(api_key, cursor=None):
    params = {
        "apiKey": api_key,
        "leagueID": LEAGUE_IDS,
        "oddsAvailable": "true",
        "limit": 50,
    }
    if cursor:
        params["cursor"] = cursor
    url = f"{API_BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_odd_id(odd_id):
    """oddID format: {statID}-{statEntityID}-{periodID}-{betTypeID}-{sideID}
    Confirmed via SportsGameOdds' own docs example:
    'assists-LEBRON_JAMES_1_NBA-game-ou-over' -- multi-word components use
    underscores internally, hyphen is strictly the between-component
    separator, so a plain split works."""
    parts = odd_id.split("-")
    if len(parts) != 5:
        return None
    stat_id, entity_id, period_id, bet_type_id, side_id = parts
    return {"statID": stat_id, "entityID": entity_id, "periodID": period_id, "betTypeID": bet_type_id, "sideID": side_id}


def main():
    api_key = os.environ.get("SPORTSGAMEODDS_API_KEY")
    if not api_key:
        print("SPORTSGAMEODDS_API_KEY not set; leaving existing file untouched.", file=sys.stderr)
        return

    fetch_log = load_json(FETCH_LOG_PATH, {})
    cutoff = (datetime.date.today() - datetime.timedelta(days=RE_FETCH_DAYS)).isoformat()

    props_by_player = {}
    printed_sample = False
    events_seen = 0
    events_used = 0
    events_skipped_recent = 0
    cursor = None

    while events_used < MAX_EVENTS_PER_RUN:
        try:
            resp = api_get(api_key, cursor)
        except urllib.error.HTTPError as e:
            # Confirmed live this was needed: the bare exception string only
            # ever showed "HTTP Error 403: Forbidden" -- the status line, not
            # the actual reason. APIs commonly put the real explanation
            # ("plan doesn't include this endpoint", "invalid key format",
            # etc.) in the response BODY, which a plain str(e) never
            # surfaces. Reading it directly here means the next failure is
            # diagnosable from the log instead of requiring another guess.
            try:
                body = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                body = "(could not read response body)"
            print(f"SportsGameOdds /events call failed: HTTP {e.code} {e.reason} -- response body: {body}", file=sys.stderr)
            break
        except Exception as e:
            print(f"SportsGameOdds /events call failed: {e}", file=sys.stderr)
            break

        events = resp.get("data", [])
        if not printed_sample and events:
            print(f"Sample SportsGameOdds event: {json.dumps(events[0])[:800]}", file=sys.stderr)
            printed_sample = True

        for event in events:
            events_seen += 1
            event_id = event.get("eventID")
            if not event_id:
                continue
            if fetch_log.get(event_id, "") >= cutoff:
                events_skipped_recent += 1
                continue
            if events_used >= MAX_EVENTS_PER_RUN:
                break

            players = event.get("players", {})
            odds = event.get("odds", {})
            for odd_id, odd_data in odds.items():
                parsed = parse_odd_id(odd_id)
                if not parsed or parsed["periodID"] != "game" or parsed["betTypeID"] != "ou":
                    continue
                stat = TARGET_STATS.get(parsed["statID"])
                if not stat:
                    continue
                player_info = players.get(parsed["entityID"])
                player_name = player_info.get("name") if player_info else None
                if not player_name:
                    continue
                line = odd_data.get("overUnder") or odd_data.get("bookOverUnder")
                if line is None:
                    continue
                try:
                    line = float(line)
                except (TypeError, ValueError):
                    continue

                by_bookmaker = odd_data.get("byBookmaker", {})
                for book_id, book_odds in by_bookmaker.items():
                    if not book_odds.get("available"):
                        continue
                    book_line = book_odds.get("overUnder")
                    try:
                        book_line = float(book_line) if book_line is not None else line
                    except (TypeError, ValueError):
                        book_line = line
                    entry_list = props_by_player.setdefault(player_name, {}).setdefault(stat, [])
                    existing = next((e for e in entry_list if e["book"] == book_id and e["line"] == book_line), None)
                    if existing:
                        if parsed["sideID"] == "over":
                            existing["overPrice"] = book_odds.get("odds")
                        else:
                            existing["underPrice"] = book_odds.get("odds")
                    else:
                        entry = {"line": book_line, "book": book_id, "overPrice": None, "underPrice": None}
                        if parsed["sideID"] == "over":
                            entry["overPrice"] = book_odds.get("odds")
                        else:
                            entry["underPrice"] = book_odds.get("odds")
                        entry_list.append(entry)

            fetch_log[event_id] = datetime.date.today().isoformat()
            events_used += 1
            if events_used >= MAX_EVENTS_PER_RUN:
                break

        cursor = resp.get("nextCursor")
        if not cursor:
            break
        time.sleep(0.2)

    print(f"Scanned {events_seen} events ({events_skipped_recent} skipped -- already fetched within the last {RE_FETCH_DAYS} days), processed {events_used} for props.", file=sys.stderr)

    if events_used == 0:
        print("No new events processed this run -- leaving existing data/player-props-odds.json untouched.", file=sys.stderr)
        return

    summary = {}
    for player, stats in props_by_player.items():
        summary[player] = {}
        for stat, entries in stats.items():
            lines = sorted(e["line"] for e in entries)
            median_line = lines[len(lines) // 2] if len(lines) % 2 else (lines[len(lines) // 2 - 1] + lines[len(lines) // 2]) / 2
            summary[player][stat] = {"line": median_line, "books": entries}

    # MERGE with existing data, same reasoning as fetch_player_props_odds.py:
    # this run only touched a subset of games, so overwriting the whole file
    # would drop every player from a game not re-fetched today.
    existing = load_json(OUT_PATH, {})
    for player, stats in summary.items():
        existing.setdefault(player, {}).update(stats)

    with open(OUT_PATH, "w") as f:
        json.dump(existing, f, indent=2)
    with open(FETCH_LOG_PATH, "w") as f:
        json.dump(fetch_log, f, indent=2)

    total_props = sum(len(stats) for stats in summary.values())
    print(f"-> {len(summary)} players, {total_props} player-prop lines updated this run. File now has {len(existing)} players total.")


if __name__ == "__main__":
    main()