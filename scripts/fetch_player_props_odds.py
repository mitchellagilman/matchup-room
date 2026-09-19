#!/usr/bin/env python3
"""
Pulls REAL sportsbook player-prop lines (passing/rushing/receiving yards)
from The Odds API and writes data/player-props-odds.json.

*** WHY THIS EXISTS ***
Confirmed live this whole session: player props were grading against the
model's OWN projected number, since no real market line existed anywhere
in this pipeline for them -- unlike team bets, which grade against a real
spread/total. That measures whether the projection is internally
consistent with itself, not whether a real bet would actually win. This
script closes that gap by pulling real lines from real sportsbooks, the
same way team bets already work.

*** WHY THIS IS A SEPARATE SCRIPT FROM fetch_odds.py ***
The Odds API's player-prop markets aren't included in the bulk /odds
endpoint fetch_odds.py already uses -- they're only accessible ONE EVENT
AT A TIME via /v4/sports/{sport}/events/{eventId}/odds. This script reads
data/odds.json (already written by fetch_odds.py, which now also stores
each game's eventId) to get the list of upcoming games and their event
IDs, then makes one additional call per event. Confirmed via The Odds
API's own documentation examples (both their NFL and NCAAF odds pages)
that current (non-historical) player-prop data is available on every
plan including free, and that the market keys are player_pass_yds,
player_rush_yds, and player_reception_yds.

Run AFTER fetch_odds.py (needs its output) and BEFORE track_predictions.py
(which reads this file's output).

*** BUDGET ***
CORRECTED, confirmed live: the real Odds API plan here is 500
requests/month, not 5,000 -- that larger number turned out to be a
different, unrelated plan (CFBD's Patreon tier). 500/month is tight
against NFL (~16 games/week) + CFB (~60+ games/week), especially stacked
on top of fetch_odds.py's own existing usage. Two mechanisms keep this
realistic: RE_FETCH_DAYS means a game already fetched recently doesn't
get re-billed every single workflow run (the original version wastefully
re-fetched the same upcoming games up to 5x/week), and MAX_EVENTS_PER_RUN
is now a true safety cap sized for this smaller budget, not the much
higher one originally assumed. Even so, full weekly coverage of both
leagues may still be tight -- worth revisiting scope (e.g. NFL-only, or
dropping one market) if actual usage runs hot against the real 500/month
limit.

*** UNVERIFIED, LIKE THE CFBD FIX WAS ***
No live key was available to test this against a real response while
writing it. Mirrors the exact structure documented on The Odds API's own
NFL/NCAAF odds pages (bookmaker -> markets -> outcomes, with
outcome.description as the player's name, outcome.point as the line,
outcome.name as Over/Under, outcome.price as the American odds) -- but
the same diagnostic-logging lesson from fetch_cfb.py's turnover-margin
fix applies: this prints the shape of the first real response so a
second guess isn't needed if something doesn't match.

Run: ODDS_API_KEY=xxxx python3 scripts/fetch_player_props_odds.py
Writes: data/player-props-odds.json
"""
import datetime
import json
import os
import sys
import time
import urllib.request
import urllib.parse

API_BASE = "https://api.the-odds-api.com/v4/sports"
ODDS_PATH = "data/odds.json"
OUT_PATH = "data/player-props-odds.json"
FETCH_LOG_PATH = "data/player-props-fetch-log.json"
MARKETS = "player_pass_yds,player_rush_yds,player_reception_yds"
MARKET_TO_STAT = {
    "player_pass_yds": "passYds",
    "player_rush_yds": "rushYds",
    "player_reception_yds": "recYds",
}
SPORT_KEY_BY_LEAGUE = {"NFL": "americanfootball_nfl", "CFB": "americanfootball_ncaaf"}
# SIZED FOR A REAL 500/MONTH PLAN, confirmed live -- the original 90-event
# cap could have burned most of a full month's quota in a SINGLE run, and
# the script re-fetched the same upcoming games every run with no memory
# of what it already had. Two changes fix this together: RE_FETCH_DAYS
# skips any game already fetched within the last few days (so a game
# sitting in 5 runs across a week only actually costs quota once, not
# five times), and this cap is now a true per-run safety limit sized for
# what's left of the budget after RE_FETCH_DAYS does its job, not a
# number picked assuming free/highvolume access.
MAX_EVENTS_PER_RUN = 20
RE_FETCH_DAYS = 3  # a game already fetched this recently is skipped -- fresh enough to catch real line movement near gameday, far enough apart that a 5x/week workflow doesn't pay for the same game 5 times


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def api_get(sport_key, event_id, api_key):
    params = {
        "apiKey": api_key,
        "regions": "us",
        "markets": MARKETS,
        "oddsFormat": "american",
    }
    url = f"{API_BASE}/{sport_key}/events/{event_id}/odds?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    api_key = os.environ.get("ODDS_API_KEY")
    if not api_key:
        print("ODDS_API_KEY not set; leaving existing file untouched.", file=sys.stderr)
        return

    odds_data = load_json(ODDS_PATH, [])
    all_games = [g for g in odds_data if g.get("eventId")]
    if not all_games:
        print("No games with an eventId found in data/odds.json (run fetch_odds.py first); nothing to do.", file=sys.stderr)
        return

    fetch_log = load_json(FETCH_LOG_PATH, {})  # eventId -> ISO date last fetched
    cutoff = (datetime.date.today() - datetime.timedelta(days=RE_FETCH_DAYS)).isoformat()
    games = [g for g in all_games if fetch_log.get(g["eventId"], "") < cutoff]
    skipped_recent = len(all_games) - len(games)
    games = games[:MAX_EVENTS_PER_RUN]
    print(f"Fetching player props for {len(games)} games ({skipped_recent} skipped -- already fetched within the last {RE_FETCH_DAYS} days)...", file=sys.stderr)

    # player_name -> stat -> list of {line, overPrice, underPrice, book}
    props_by_player = {}
    printed_sample = False
    fetched = 0
    errored = 0

    for g in games:
        sport_key = SPORT_KEY_BY_LEAGUE.get(g.get("league"))
        if not sport_key:
            continue
        try:
            event = api_get(sport_key, g["eventId"], api_key)
        except Exception as e:
            errored += 1
            # DIAGNOSTIC, same lesson as fetch_cfb.py's turnover-margin fix
            # and this script's own sample-response print below: confirmed
            # live this was needed -- a run that failed on every single
            # event previously gave no indication why (rate limit? auth?
            # bad event id?), just a bare error count. Printing the first
            # real exception message means the next failure is diagnosable
            # from the log directly instead of requiring another guess.
            if errored == 1:
                print(f"First event-odds call failed (of {len(games)} attempted): {e}", file=sys.stderr)
            continue
        fetched += 1
        fetch_log[g["eventId"]] = datetime.date.today().isoformat()

        if not printed_sample:
            # DIAGNOSTIC, same lesson as fetch_cfb.py's turnover-margin fix:
            # print the real shape once so a wrong assumption is visible
            # immediately in the workflow log instead of silently
            # producing an empty or wrong result.
            print(f"Sample player-props event response: {json.dumps(event)[:800]}", file=sys.stderr)
            printed_sample = True

        for book in event.get("bookmakers", []):
            book_name = book.get("title") or book.get("key")
            for market in book.get("markets", []):
                stat = MARKET_TO_STAT.get(market.get("key"))
                if not stat:
                    continue
                # Outcomes come as separate Over/Under rows for the same
                # player+line -- pair them up by (player, point).
                by_player_point = {}
                for o in market.get("outcomes", []):
                    player = o.get("description")
                    point = o.get("point")
                    if not player or point is None:
                        continue
                    key = (player, point)
                    entry = by_player_point.setdefault(key, {"line": point, "book": book_name, "overPrice": None, "underPrice": None})
                    if o.get("name") == "Over":
                        entry["overPrice"] = o.get("price")
                    elif o.get("name") == "Under":
                        entry["underPrice"] = o.get("price")
                for (player, point), entry in by_player_point.items():
                    props_by_player.setdefault(player, {}).setdefault(stat, []).append(entry)
        time.sleep(0.2)  # spread out requests

    # Reduce each player+stat's book list down to a usable summary: the
    # median line across books (a reasonable consensus that resists one
    # outlier book) plus the full per-book list for "line shopping"
    # display, the same philosophy fetch_odds.py already applies to team
    # markets.
    summary = {}
    for player, stats in props_by_player.items():
        summary[player] = {}
        for stat, entries in stats.items():
            lines = sorted(e["line"] for e in entries)
            median_line = lines[len(lines) // 2] if len(lines) % 2 else (lines[len(lines) // 2 - 1] + lines[len(lines) // 2]) / 2
            summary[player][stat] = {"line": median_line, "books": entries}

    # SAFETY CHECK, confirmed live this was needed: a run where every
    # single event call failed (rate limit, transient API issue, etc.)
    # would otherwise silently overwrite a previous GOOD file with an
    # empty one -- the exact opposite of what should happen when a run
    # goes badly. If fewer than half the attempted events actually
    # succeeded, treat this as a failed run and leave the existing file
    # untouched rather than erase real data with nothing.
    if games and fetched < len(games) / 2:
        print(f"Only {fetched}/{len(games)} events succeeded -- treating this as a failed run and leaving the existing {OUT_PATH} untouched rather than overwrite it with incomplete data.", file=sys.stderr)
        return

    # MERGE with existing data rather than replace it -- confirmed live
    # this matters now that RE_FETCH_DAYS/MAX_EVENTS_PER_RUN mean each run
    # only touches a SUBSET of games. Overwriting the whole file with just
    # this run's summary would silently drop every player from a game
    # that wasn't re-fetched today, even though that data is still fresh
    # and valid. Only the players/stats actually touched this run get
    # replaced; everything else carries forward untouched.
    existing = load_json(OUT_PATH, {})
    for player, stats in summary.items():
        existing.setdefault(player, {}).update(stats)

    with open(OUT_PATH, "w") as f:
        json.dump(existing, f, indent=2)
    with open(FETCH_LOG_PATH, "w") as f:
        json.dump(fetch_log, f, indent=2)

    total_props = sum(len(stats) for stats in summary.values())
    print(f"Fetched {fetched} events ({errored} errored) -> {len(summary)} players, {total_props} player-prop lines updated this run. File now has {len(existing)} players total.")


if __name__ == "__main__":
    main()