#!/usr/bin/env python3
"""
Pulls current NFL + NCAAF odds (moneyline, spread, total) from The Odds API
and writes data/odds.json.

Free tier: sign up at https://the-odds-api.com, no card required. Set the
key as the ODDS_API_KEY environment variable (the GitHub Actions workflow
reads this from a repo secret of the same name). Verify current free-tier
limits on their pricing page -- they've changed before and may again;
this script requests both leagues in one call each to stay well under
whatever the current monthly allowance is.

Run: ODDS_API_KEY=xxxx python3 scripts/fetch_odds.py
Writes: data/odds.json
"""
import json
import os
import sys
import urllib.request
import urllib.parse

API_BASE = "https://api.the-odds-api.com/v4/sports"
EXISTING_PATH = "data/odds.json"

SPORTS = {
    "NFL": "americanfootball_nfl",
    "CFB": "americanfootball_ncaaf",
}


def api_get(sport_key, api_key):
    params = {
        "apiKey": api_key,
        "regions": "us",
        "markets": "h2h,spreads,totals",
        "oddsFormat": "american",
    }
    url = f"{API_BASE}/{sport_key}/odds?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_game(event, league):
    home, away = event.get("home_team"), event.get("away_team")
    bookmakers = event.get("bookmakers", [])
    if not bookmakers:
        return None
    book = bookmakers[0]  # first available book; good enough for a weekly snapshot
    markets = {m["key"]: m for m in book.get("markets", [])}

    def outcome(market_key, team_name):
        m = markets.get(market_key)
        if not m:
            return None
        for o in m.get("outcomes", []):
            if o.get("name") == team_name:
                return o
        return None

    h2h_home = outcome("h2h", home)
    h2h_away = outcome("h2h", away)
    spread_home = outcome("spreads", home)
    spread_away = outcome("spreads", away)
    totals = markets.get("totals", {}).get("outcomes", [])
    over = next((o for o in totals if o.get("name") == "Over"), None)
    under = next((o for o in totals if o.get("name") == "Under"), None)

    if not (h2h_home and h2h_away):
        return None

    return {
        "game": f"{away} @ {home}",
        "league": league,
        "date": event.get("commence_time", "")[:10],
        "aTeam": away, "aML": h2h_away.get("price"),
        "aSpread": spread_away.get("point") if spread_away else None,
        "aSpreadOdds": spread_away.get("price") if spread_away else None,
        "bTeam": home, "bML": h2h_home.get("price"),
        "bSpread": spread_home.get("point") if spread_home else None,
        "bSpreadOdds": spread_home.get("price") if spread_home else None,
        "total": over.get("point") if over else None,
        "overOdds": over.get("price") if over else None,
        "underOdds": under.get("price") if under else None,
    }


def main():
    api_key = os.environ.get("ODDS_API_KEY")
    if not api_key:
        print("ODDS_API_KEY is not set -- skipping odds update.", file=sys.stderr)
        return

    games = []
    for league, sport_key in SPORTS.items():
        try:
            events = api_get(sport_key, api_key)
        except Exception as e:
            print(f"Could not fetch {league} odds ({e}); skipping.", file=sys.stderr)
            continue
        for event in events:
            g = extract_game(event, league)
            if g:
                games.append(g)

    if not games:
        print("No games returned -- leaving existing odds.json untouched.", file=sys.stderr)
        return

    with open(EXISTING_PATH, "w") as f:
        json.dump(games, f, indent=2)
    print(f"Wrote {len(games)} games to {EXISTING_PATH}")


if __name__ == "__main__":
    main()