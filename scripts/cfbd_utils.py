#!/usr/bin/env python3
"""
Shared CollegeFootballData (CFBD) API helper, used by every CFB-related
fetch script in this project (fetch_cfb.py, fetch_cfb_ratings.py,
fetch_cfb_schedule.py, fetch_cfb_rosters.py, fetch_players_cfb.py,
track_predictions.py).

*** WHY THIS EXISTS ***
Confirmed live (real Action run, Sept 2026): running all the CFB scripts
back-to-back in one workflow job -- especially after the FCS expansion,
which roughly doubled the number of CFBD calls (every FBS request now has
a matching FCS request) -- triggers real HTTP 429 "Too Many Requests"
responses from CFBD. Every single CFB script failed in that run, all with
the same 429 error, while every non-CFBD script (NFL, odds, injuries) in
the exact same run worked fine. That points squarely at CFBD's rate limit,
not a per-script bug.

cfbd_get() retries on 429 with backoff (honoring a Retry-After header if
CFBD sends one, otherwise a fixed escalating wait) before giving up. This
doesn't eliminate the possibility of hitting a rate limit -- if CFBD's
limit is low enough, or the outage is long enough, retries can still be
exhausted -- but it should absorb the kind of short-window burst seen in
that real run. Each script's own try/except around its cfbd_get() calls
still applies afterward exactly as before: if retries are exhausted, that
script logs why and leaves its existing data file untouched, same
graceful-degradation behavior as always.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.collegefootballdata.com"
MAX_RETRIES = 4
RETRY_WAIT_SECONDS = [5, 15, 30, 60]  # escalating backoff if CFBD doesn't send Retry-After


def cfbd_get(path, params, api_key, timeout=30):
    """GET a CFBD endpoint, retrying with backoff on HTTP 429. Raises on
    any other error, or if retries are exhausted, exactly like a plain
    urlopen call would -- callers keep their existing try/except as-is."""
    url = f"{API_BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    })
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == MAX_RETRIES:
                raise
            retry_after = e.headers.get("Retry-After") if e.headers else None
            try:
                wait = float(retry_after) if retry_after else RETRY_WAIT_SECONDS[min(attempt, len(RETRY_WAIT_SECONDS) - 1)]
            except (TypeError, ValueError):
                wait = RETRY_WAIT_SECONDS[min(attempt, len(RETRY_WAIT_SECONDS) - 1)]
            print(f"CFBD rate-limited on {path} (attempt {attempt+1}/{MAX_RETRIES+1}); waiting {wait:.0f}s before retry...", flush=True)
            time.sleep(wait)
            last_error = e
    if last_error:
        raise last_error
