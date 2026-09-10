#!/usr/bin/env python3
"""
Shared CollegeFootballData (CFBD) API helper, used by every CFB-related
fetch script in this project (fetch_cfb.py, fetch_cfb_ratings.py,
fetch_cfb_schedule.py, fetch_cfb_rosters.py, fetch_players_cfb.py,
track_predictions.py).

*** REVISED AFTER A REAL FAILED RUN -- READ THIS ***
An earlier version of this file assumed CFBD's 429s were a short
burst-window rate limit and retried with up to ~110 seconds of backoff.
That assumption was wrong. Confirmed via CFBD's own published terms:
the free tier is 1,000 API calls per CALENDAR MONTH, not a short-term
rate limit -- and a real run showed every single call still failing
with 429 even after the full backoff, which is exactly what monthly
quota exhaustion looks like (retrying within the same run cannot help;
the quota doesn't reset until next month). Worse, that version's
retries likely burned MORE quota for nothing on every failed run.

cfbd_get() now reads the 429 response body. CFBD's real quota-exceeded
response is confirmed (via a public GitHub issue against their own repo)
to read {"message":"Monthly call quota exceeded"} -- when the body
contains "quota", this raises immediately with NO retry, since retrying
a monthly quota is pointless and wasteful. A 429 WITHOUT "quota" in the
body is treated as a genuine short-term rate limit and still gets the
backoff/retry treatment, since that distinction is real and worth
keeping -- just don't conflate the two anymore.

If you're seeing "quota" errors, check your usage at
https://collegefootballdata.com (account dashboard) to confirm; the fix
from here is either wait for next month's reset, reduce how many calls
this pipeline makes per run, or upgrade the Patreon tier for more calls.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.collegefootballdata.com"
MAX_RETRIES = 3
RETRY_WAIT_SECONDS = [5, 15, 30]  # escalating backoff -- only used for genuine short-term 429s, not quota exhaustion


def cfbd_get(path, params, api_key, timeout=30):
    """GET a CFBD endpoint. On HTTP 429, checks whether the response body
    says the MONTHLY quota is exhausted (raises immediately, no retry --
    see module docstring) versus a genuine short-term rate limit (retries
    with backoff). Raises on any other error, or if retries are
    exhausted, exactly like a plain urlopen call would -- callers keep
    their existing try/except as-is.

    Also prints any response header whose name contains "ratelimit" or
    "quota" on every call (success or failure) -- CFBD's docs mention a
    dedicated usage/rate-limit reference but don't spell out exact header
    names anywhere findable, and the website itself doesn't surface a
    usage dashboard. Rather than guess header names that might not
    exist, this just surfaces whatever CFBD actually sends back, so the
    real answer shows up in the Action log from a real call instead of
    from more searching."""
    url = f"{API_BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    })
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                _print_quota_headers(path, resp.headers)
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            _print_quota_headers(path, e.headers)
            if e.code != 429:
                raise
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            if "quota" in body.lower():
                print(f"CFBD monthly quota exhausted on {path} -- not retrying (retrying a monthly quota can't help, and only wastes more of it). Check usage at https://collegefootballdata.com", flush=True)
                raise
            if attempt == MAX_RETRIES:
                raise
            wait = RETRY_WAIT_SECONDS[min(attempt, len(RETRY_WAIT_SECONDS) - 1)]
            print(f"CFBD rate-limited on {path} (attempt {attempt+1}/{MAX_RETRIES+1}); waiting {wait:.0f}s before retry...", flush=True)
            time.sleep(wait)
            last_error = e
    if last_error:
        raise last_error


def _print_quota_headers(path, headers):
    if not headers:
        return
    found = [(k, v) for k, v in headers.items() if "ratelimit" in k.lower() or "quota" in k.lower()]
    if found:
        print(f"CFBD usage headers on {path}: " + ", ".join(f"{k}={v}" for k, v in found), flush=True)
