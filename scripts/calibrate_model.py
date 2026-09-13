#!/usr/bin/env python3
"""
Uses the accumulated track record to calibrate confidence-tier edge
thresholds over time -- a real, grounded form of "the model gets smarter,"
grounded in this app's own actual hit/miss history, not a vague ML claim.

*** CALIBRATED PER LEAGUE, NOT POOLED ***
Confirmed live: CFB and NFL picks were being pooled into one combined hit
rate. That's the wrong signal to act on -- if CFB is genuinely struggling
while NFL is doing fine (or vice versa), a blended number dilutes the
real, league-specific problem and calibrates neither league correctly.
Each league now gets its own sample size, its own hit rate, and its own
thresholds, entirely independent of how the other league is doing.

HOW: computes each league's historical hit rate for its own graded team
bets (spread/total; player props are excluded -- they grade against the
model's own projected number, not a real market line, so their hit rate
measures something different and mixing the two would muddy the signal).

Requires MIN_SAMPLE_SIZE graded picks PER LEAGUE before trusting
anything -- below that, there's no real statistical signal for that
league, just noise, and that league's block writes "calibrated": false.
index.html falls back to that league's original, hardcoded thresholds
(Strong >=7, Moderate >=3.5) whenever that's the case, so nothing changes
for a league until there's real data behind it -- one league reaching the
sample threshold doesn't affect the other at all.

Once a league has enough picks: a hit rate meaningfully ABOVE baseline
nudges that league's edge thresholds DOWN slightly (the model's edge
signal is working there -- trust smaller edges a bit more). A hit rate
meaningfully BELOW baseline nudges them UP (be more conservative about
what counts as "Strong" for that league specifically).

This is intentionally simple and conservative -- one global nudge per
league, not per-tier optimization -- specifically because regressing
tier-by-tier on a small sample would fit noise, not a real pattern. As
each league's sample size grows, a more granular per-tier calibration
would become worth building; this is the first, honestly-scoped version.

Run: python3 scripts/calibrate_model.py
Writes: data/calibration.json
"""
import json
import datetime

TRACK_PATH = "data/track-record.json"
OUT_PATH = "data/calibration.json"
MIN_SAMPLE_SIZE = 30  # below this, there's no real statistical signal for that league -- don't touch anything
BASELINE_HIT_RATE = 0.55  # what we'd expect from a model doing nothing useful. Not 50% -- real vig means "no real edge" would actually net a bit under 50% long-run, so 55% is a deliberately generous bar that avoids over-reacting to ordinary noise
NUDGE_PER_10PCT = 0.5  # how many points to shift thresholds per 10 percentage points of deviation from baseline
DEFAULT_STRONG = 7.0
DEFAULT_MODERATE = 3.5
LEAGUES = ["NFL", "CFB"]


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def calibrate_league(graded):
    sample_size = len(graded)
    block = {
        "sample_size": sample_size,
        "min_sample_size": MIN_SAMPLE_SIZE,
        "calibrated": False,
        "strong_threshold": DEFAULT_STRONG,
        "moderate_threshold": DEFAULT_MODERATE,
    }
    if sample_size >= MIN_SAMPLE_SIZE:
        hits = sum(1 for p in graded if p["status"] == "hit")
        hit_rate = hits / sample_size
        deviation_pct = (hit_rate - BASELINE_HIT_RATE) * 100
        nudge = (deviation_pct / 10) * NUDGE_PER_10PCT
        block["calibrated"] = True
        block["hit_rate"] = round(hit_rate, 3)
        block["deviation_pct"] = round(deviation_pct, 1)
        block["strong_threshold"] = round(max(3.0, DEFAULT_STRONG - nudge), 2)
        block["moderate_threshold"] = round(max(1.5, DEFAULT_MODERATE - nudge), 2)
    return block


def main():
    record = load_json(TRACK_PATH, {"picks": []})
    team_picks = [p for p in record["picks"] if p.get("type") in ("spread", "total")]

    calibration = {"last_updated": datetime.date.today().isoformat()}
    summary_lines = []
    for league in LEAGUES:
        graded = [p for p in team_picks if p.get("league") == league and p.get("status") in ("hit", "miss")]
        block = calibrate_league(graded)
        calibration[league] = block
        if block["calibrated"]:
            summary_lines.append(
                f"{league}: calibrated from {block['sample_size']} graded picks, hit rate "
                f"{block['hit_rate']*100:.1f}% (baseline {BASELINE_HIT_RATE*100:.0f}%) -> "
                f"Strong {block['strong_threshold']}, Moderate {block['moderate_threshold']}"
            )
        else:
            summary_lines.append(
                f"{league}: only {block['sample_size']} graded picks so far (need {MIN_SAMPLE_SIZE}+) -- "
                f"using original hardcoded thresholds"
            )

    with open(OUT_PATH, "w") as f:
        json.dump(calibration, f, indent=2)

    print(" | ".join(summary_lines))


if __name__ == "__main__":
    main() 