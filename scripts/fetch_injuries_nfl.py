#!/usr/bin/env python3
"""
Pulls the current week's NFL injury report (questionable/doubtful/out) from
nflverse and writes data/nfl-injuries.json.

*** VERIFIED LIVE ***
Unlike several other scripts in this project, this one WAS verified
against a real live response while being built: fetched
injuries_2026.csv directly, confirmed it has real rows with
report_status values of "Questionable" and "Out" (real Week 1 2026
data), and confirmed the column names below match exactly.

*** NO CFB EQUIVALENT ***
There is no fetch_injuries_cfb.py, and there isn't going to be one from
this data source -- checked CollegeFootballData's full endpoint list,
official docs, and third-party API wrappers (cfbfastR, the official
cfbd-python client) and there is no injuries endpoint anywhere. This
matches reality: college football has no NCAA-mandated weekly injury
report the way the NFL does, so there's no standardized data to pull
regardless of source. The CFB Injuries tab in the app explains this
directly rather than silently having no tab at all.

Source (verified): https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{YEAR}.csv

Run: python3 scripts/fetch_injuries_nfl.py
Writes: data/nfl-injuries.json
"""
import csv
import io
import json
import sys
import urllib.request

YEAR = 2026
INJURIES_URL = f"https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{YEAR}.csv"
OUT_PATH = "data/nfl-injuries.json"

TEAM_NAME_MAP = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills", "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs", "LAC": "Los Angeles Chargers", "LA": "Los Angeles Rams",
    "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins", "MIN": "Minnesota Vikings",
    "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers",
    "SEA": "Seattle Seahawks", "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}


def fetch_csv(url):
    req = urllib.request.Request(url, headers={"User-Agent": "matchup-room-fetcher"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(raw)))


def main():
    try:
        rows = fetch_csv(INJURIES_URL)
    except Exception as e:
        print(f"Could not fetch injuries_{YEAR}.csv ({e}); leaving existing file untouched.", file=sys.stderr)
        return

    if not rows:
        print("Injury report came back empty; leaving existing file untouched.", file=sys.stderr)
        return

    # Only this week (the most recent week present) -- a season-long file
    # would otherwise pile up every past week's report too.
    weeks = [int(r["week"]) for r in rows if (r.get("week") or "").isdigit()]
    if not weeks:
        print("Could not find a week number in the injuries file; leaving existing file untouched.", file=sys.stderr)
        return
    current_week = max(weeks)

    out = []
    for r in rows:
        if not (r.get("week") or "").isdigit() or int(r["week"]) != current_week:
            continue
        status = (r.get("report_status") or "").strip()
        if status not in ("Questionable", "Doubtful", "Out"):
            continue  # everything else is practice-participation-only noise, not a game-status designation
        team_abbr = r.get("team", "")
        out.append({
            "team": TEAM_NAME_MAP.get(team_abbr, team_abbr),
            "name": r.get("full_name", ""),
            "pos": r.get("position", ""),
            "injury": r.get("report_primary_injury", "") or "Not specified",
            "status": status,
            "_id": r.get("gsis_id", ""),
        })

    with open(OUT_PATH, "w") as f:
        json.dump({"week": current_week, "entries": out}, f, indent=2)

    by_status = {}
    for e in out:
        by_status[e["status"]] = by_status.get(e["status"], 0) + 1
    print(f"Wrote {len(out)} NFL injury report entries for week {current_week} to {OUT_PATH} "
          f"({', '.join(f'{k}: {v}' for k, v in sorted(by_status.items()))})")


if __name__ == "__main__":
    main()
