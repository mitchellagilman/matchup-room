#!/usr/bin/env python3
"""
Pulls current NFL + NCAAF odds from The Odds API and writes data/odds.json.

Unlike the original version (which only looked at the first bookmaker
returned), this scans EVERY bookmaker for each game and keeps the best
available price on each side -- this is "line shopping", one of the
highest-value habits in betting, often worth more than any predictive
edge. The top-level fields (aML, bML, aSpreadOdds, etc.) are now each
the best price found across all books, with a matching *Book field
naming which book offered it. A full per-book breakdown is kept in the
"books" array so the UI can show a real comparison table, not just the
winner.

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


def find_outcome(market, team_name):
    if not market:
        return None
    for o in market.get("outcomes", []):
        if o.get("name") == team_name:
            return o
    return None


def extract_game(event, league):
    home, away = event.get("home_team"), event.get("away_team")
    bookmakers = event.get("bookmakers", [])
    if not bookmakers:
        return None

    books_out = []
    # (best_price, book_name) per market -- higher American odds is always
    # better for the bettor regardless of favorite/underdog (-105 beats
    # -110; +150 beats +140), so "best" is just max() of the raw price.
    best = {k: (None, None) for k in ["aML", "bML", "aSpreadOdds", "bSpreadOdds", "overOdds", "underOdds"]}
    primary_points = {"aSpread": None, "bSpread": None, "total": None}

    for book in bookmakers:
        markets = {m["key"]: m for m in book.get("markets", [])}
        h2h_a = find_outcome(markets.get("h2h"), away)
        h2h_b = find_outcome(markets.get("h2h"), home)
        sp_a = find_outcome(markets.get("spreads"), away)
        sp_b = find_outcome(markets.get("spreads"), home)
        totals = markets.get("totals", {}).get("outcomes", [])
        over = next((o for o in totals if o.get("name") == "Over"), None)
        under = next((o for o in totals if o.get("name") == "Under"), None)

        book_name = book.get("title") or book.get("key")
        entry = {
            "book": book_name,
            "aML": h2h_a.get("price") if h2h_a else None,
            "bML": h2h_b.get("price") if h2h_b else None,
            "aSpread": sp_a.get("point") if sp_a else None,
            "aSpreadOdds": sp_a.get("price") if sp_a else None,
            "bSpread": sp_b.get("point") if sp_b else None,
            "bSpreadOdds": sp_b.get("price") if sp_b else None,
            "total": over.get("point") if over else None,
            "overOdds": over.get("price") if over else None,
            "underOdds": under.get("price") if under else None,
        }
        books_out.append(entry)

        if primary_points["aSpread"] is None and entry["aSpread"] is not None:
            primary_points["aSpread"] = entry["aSpread"]
            primary_points["bSpread"] = entry["bSpread"]
        if primary_points["total"] is None and entry["total"] is not None:
            primary_points["total"] = entry["total"]

        for key in best:
            price = entry.get(key)
            if price is None:
                continue
            cur_best, _ = best[key]
            if cur_best is None or price > cur_best:
                best[key] = (price, book_name)

    if best["aML"][0] is None or best["bML"][0] is None:
        return None

    return {
        "game": f"{away} @ {home}",
        "league": league,
        "date": event.get("commence_time", "")[:10],
        "aTeam": away, "aML": best["aML"][0], "aMLBook": best["aML"][1],
        "aSpread": primary_points["aSpread"], "aSpreadOdds": best["aSpreadOdds"][0], "aSpreadOddsBook": best["aSpreadOdds"][1],
        "bTeam": home, "bML": best["bML"][0], "bMLBook": best["bML"][1],
        "bSpread": primary_points["bSpread"], "bSpreadOdds": best["bSpreadOdds"][0], "bSpreadOddsBook": best["bSpreadOdds"][1],
        "total": primary_points["total"], "overOdds": best["overOdds"][0], "overOddsBook": best["overOdds"][1],
        "underOdds": best["underOdds"][0], "underOddsBook": best["underOdds"][1],
        "books": books_out,
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
    book_counts = [len(g.get("books", [])) for g in games]
    avg_books = sum(book_counts) / len(book_counts) if book_counts else 0
    print(f"Wrote {len(games)} games to {EXISTING_PATH} (avg {avg_books:.1f} books compared per game)")


if __name__ == "__main__":
    main()
