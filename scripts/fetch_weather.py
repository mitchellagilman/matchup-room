#!/usr/bin/env python3
"""
Pulls real weather forecasts for upcoming NFL games from the National
Weather Service (api.weather.gov) -- free, no API key required. Writes
data/weather.json, keyed by home team name.

*** WHY THIS EXISTS ***
Wind, cold, and precipitation are real, well-documented factors in NFL
scoring -- wind hurts passing accuracy and kicking distance, cold
suppresses scoring somewhat, rain/snow increases fumbles. Nothing in
this pipeline previously had any way to know whether a given week's
games were being played in a dome or a blizzard.

*** SCOPE: NFL ONLY ***
Deliberately not built for CFB in this first version -- CFB has 130+
teams across FBS+FCS, and hand-building an accurate stadium-location
table at that scale is a much bigger undertaking than the 32 fixed NFL
stadiums. Worth adding later if this proves valuable, starting with just
the ranked/major programs rather than the full slate.

*** DOME HANDLING ***
Indoor and fixed-roof stadiums (and retractable-roof stadiums that are
closed the large majority of the time) are marked "dome": true below and
skipped entirely -- there's no real weather exposure to check for a game
that isn't happening outdoors. STADIUM_LOCATIONS reflects each team's
real home venue as of this writing; stadium names change fairly often
(naming-rights deals), so the coordinates (which don't change) are what
actually matters here, not getting every current sponsor name right.

*** API FLOW ***
api.weather.gov requires two calls per location: /points/{lat},{lon}
returns a forecast URL specific to that location's grid point, then that
URL returns the actual period-by-period forecast (temperature, wind,
short description). Confirmed via NWS's own public API documentation
structure; this is a stable, long-standing government API, not a new or
unverified one like the other integrations this session.

Run: python3 scripts/fetch_weather.py
Writes: data/weather.json
"""
import datetime
import json
import re
import sys
import time
import urllib.request
import urllib.error

SCHEDULE_PATH = "data/nfl-schedule.json"
OUT_PATH = "data/weather.json"
USER_AGENT = "matchup-room-fetcher (contact: github.com/mitchellagilman/matchup-room)"  # NWS API requires a real User-Agent identifying the application, not a browser-style one

# team name (as used elsewhere in this app) -> {lat, lon, dome}
# Coordinates are approximate stadium/city locations -- accurate enough
# for weather purposes, since NWS forecasts are gridded at a city/region
# level, not pinpoint-stadium precision anyway.
STADIUM_LOCATIONS = {
    "Arizona Cardinals": {"lat": 33.5276, "lon": -112.2626, "dome": True},
    "Atlanta Falcons": {"lat": 33.7554, "lon": -84.4008, "dome": True},
    "Baltimore Ravens": {"lat": 39.2780, "lon": -76.6227, "dome": False},
    "Buffalo Bills": {"lat": 42.7738, "lon": -78.7870, "dome": False},
    "Carolina Panthers": {"lat": 35.2258, "lon": -80.8528, "dome": False},
    "Chicago Bears": {"lat": 41.8623, "lon": -87.6167, "dome": False},
    "Cincinnati Bengals": {"lat": 39.0954, "lon": -84.5160, "dome": False},
    "Cleveland Browns": {"lat": 41.5061, "lon": -81.6995, "dome": False},
    "Dallas Cowboys": {"lat": 32.7473, "lon": -97.0945, "dome": True},
    "Denver Broncos": {"lat": 39.7439, "lon": -105.0201, "dome": False},
    "Detroit Lions": {"lat": 42.3400, "lon": -83.0456, "dome": True},
    "Green Bay Packers": {"lat": 44.5013, "lon": -88.0622, "dome": False},
    "Houston Texans": {"lat": 29.6847, "lon": -95.4107, "dome": True},
    "Indianapolis Colts": {"lat": 39.7601, "lon": -86.1639, "dome": True},
    "Jacksonville Jaguars": {"lat": 30.3239, "lon": -81.6373, "dome": False},
    "Kansas City Chiefs": {"lat": 39.0489, "lon": -94.4839, "dome": False},
    "Las Vegas Raiders": {"lat": 36.0909, "lon": -115.1833, "dome": True},
    "Los Angeles Chargers": {"lat": 33.9535, "lon": -118.3392, "dome": True},
    "Los Angeles Rams": {"lat": 33.9535, "lon": -118.3392, "dome": True},
    "Miami Dolphins": {"lat": 25.9580, "lon": -80.2389, "dome": False},
    "Minnesota Vikings": {"lat": 44.9738, "lon": -93.2577, "dome": True},
    "New England Patriots": {"lat": 42.0909, "lon": -71.2643, "dome": False},
    "New Orleans Saints": {"lat": 29.9511, "lon": -90.0812, "dome": True},
    "New York Giants": {"lat": 40.8135, "lon": -74.0745, "dome": False},
    "New York Jets": {"lat": 40.8135, "lon": -74.0745, "dome": False},
    "Philadelphia Eagles": {"lat": 39.9008, "lon": -75.1675, "dome": False},
    "Pittsburgh Steelers": {"lat": 40.4468, "lon": -80.0158, "dome": False},
    "San Francisco 49ers": {"lat": 37.4030, "lon": -121.9700, "dome": False},
    "Seattle Seahawks": {"lat": 47.5952, "lon": -122.3316, "dome": False},
    "Tampa Bay Buccaneers": {"lat": 27.9759, "lon": -82.5033, "dome": False},
    "Tennessee Titans": {"lat": 36.1665, "lon": -86.7713, "dome": False},
    "Washington Commanders": {"lat": 38.9078, "lon": -76.8645, "dome": False},
}


def api_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_forecast_for_location(lat, lon):
    points = api_get(f"https://api.weather.gov/points/{lat},{lon}")
    forecast_url = points.get("properties", {}).get("forecast")
    if not forecast_url:
        return None
    forecast = api_get(forecast_url)
    return forecast.get("properties", {}).get("periods", [])


def pick_period_for_date(periods, game_date):
    """NWS returns periods like 'Thursday', 'Thursday Night', 'Friday'
    rather than exact dates -- matches by parsing each period's own
    startTime field (an ISO datetime) against the game's date instead of
    trying to parse the human-readable name field."""
    if not game_date:
        return periods[0] if periods else None
    for p in periods:
        start = (p.get("startTime") or "")[:10]
        if start == game_date:
            return p
    return periods[0] if periods else None


def classify_severity(period):
    if not period:
        return None
    wind_str = period.get("windSpeed") or ""
    # windSpeed often comes as a range ("6 to 14 mph"), confirmed via NWS's
    # own real example responses -- taking the max of all numbers found
    # (not just the first match) means a "6 to 14 mph" reading correctly
    # registers as 14, not the less-informative lower bound of 6.
    wind_numbers = [int(n) for n in re.findall(r"\d+", wind_str)]
    wind_mph = max(wind_numbers) if wind_numbers else 0
    temp = period.get("temperature")
    short_forecast = (period.get("shortForecast") or "").lower()
    # FIX, confirmed live against real coverage of an actual game: light,
    # forecasted rain ("Sunday shower", "Light Rain") was being treated the
    # same as heavy/torrential rain -- real analysts covering that exact
    # game described light rain and single-digit wind as something that
    # "likely will not impact too much of the game," but the old any()
    # check would have flagged it severe anyway just because "rain"
    # appeared in the text at all, regardless of how light. Now requires
    # either an explicit heavy/intensity word, or "rain"/"snow" combined
    # with at least moderately elevated wind -- light rain on a calm day
    # no longer trips this alone, matching how real coverage actually
    # distinguishes these games.
    heavy_precip = any(w in short_forecast for w in ["heavy", "torrential", "downpour", "severe thunderstorm", "blizzard"])
    any_precip = any(w in short_forecast for w in ["rain", "snow", "storm", "shower"])
    precip = heavy_precip or (any_precip and wind_mph >= 15)

    severe = wind_mph >= 20 or precip or (isinstance(temp, (int, float)) and temp <= 20)
    return {
        "windMph": wind_mph, "tempF": temp, "shortForecast": period.get("shortForecast"),
        "severe": severe,
    }


def main():
    sched = {}
    try:
        with open(SCHEDULE_PATH) as f:
            sched = json.load(f)
    except FileNotFoundError:
        print(f"{SCHEDULE_PATH} not found; nothing to do.", file=sys.stderr)
        return

    games = sched.get("games", [])
    results = {}
    checked = 0
    errored = 0

    for g in games:
        if g.get("awayScore") is not None:
            continue  # already played
        home = g.get("b") or g.get("home")
        if not home:
            continue
        loc = STADIUM_LOCATIONS.get(home)
        if not loc:
            continue
        if loc["dome"]:
            results[home] = {"dome": True}
            continue
        try:
            periods = get_forecast_for_location(loc["lat"], loc["lon"])
            period = pick_period_for_date(periods, g.get("date"))
            weather = classify_severity(period)
            if weather:
                weather["dome"] = False
                results[home] = weather
            checked += 1
        except Exception as e:
            errored += 1
            if errored == 1:
                print(f"First weather lookup failed (of remaining outdoor games): {e}", file=sys.stderr)
        time.sleep(0.3)

    if checked == 0 and errored > 0:
        print(f"All {errored} weather lookups failed -- leaving existing {OUT_PATH} untouched rather than overwrite it with nothing.", file=sys.stderr)
        return

    with open(OUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    severe_count = sum(1 for v in results.values() if v.get("severe"))
    print(f"Checked {checked} outdoor games ({errored} errored), {len(results)} teams total (including domes) -> {severe_count} flagged severe. Written to {OUT_PATH}")


if __name__ == "__main__":
    main()