#!/usr/bin/env python3
"""
Uses the accumulated track record to calibrate confidence-tier edge
thresholds over time -- a real, grounded form of "the model gets smarter,"
grounded in this app's own actual hit/miss history, not a vague ML claim.

HOW: computes the overall historical hit rate for graded team bets
(spread/total; player props are excluded -- they grade against the
model's own projected number, not a real market line, so their hit rate
measures something different and mixing the two would muddy the signal).

Requires MIN_SAMPLE_SIZE graded picks before trusting anything -- below
that, there's no real statistical signal, just noise, and this writes
"calibrated": false. index.html falls back to its original, hardcoded
thresholds (Strong >=7, Moderate >=3.5) whenever that's the case, so nothing
changes behavior until there's real data behind it.

Once enough picks exist: a hit rate meaningfully ABOVE baseline nudges
the edge thresholds DOWN slightly (the model's edge signal is working --
trust smaller edges a bit more). A hit rate meaningfully BELOW baseline
nudges them UP (be more conservative about what counts as "Strong").

This is intentionally simple and conservative -- one global nudge, not
per-tier optimization -- specifically because regressing tier-by-tier on
a small sample would fit noise, not a real pattern. As the season goes on
and sample size grows, a more granular per-tier calibration would become
worth building; this is the first, honestly-scoped version.

Run: python3 scripts/calibrate_model.py
Writes: data/calibration.json
"""
import json
import datetime

TRACK_PATH = "data/track-record.json"
OUT_PATH = "data/calibration.json"
MIN_SAMPLE_SIZE = 30  # below this, there's no real statistical signal -- don't touch anything
BASELINE_HIT_RATE = 0.55  # what we'd expect from a model doing nothing useful. Not 50% -- real vig means "no real edge" would actually net a bit under 50% long-run, so 55% is a deliberately generous bar that avoids over-reacting to ordinary noise
NUDGE_PER_10PCT = 0.5  # how many points to shift thresholds per 10 percentage points of deviation from baseline
DEFAULT_STRONG = 7.0
DEFAULT_MODERATE = 3.5


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def main():
    record = load_json(TRACK_PATH, {"picks": []})
    team_picks = [p for p in record["picks"] if p.get("type") in ("spread", "total")]
    graded = [p for p in team_picks if p.get("status") in ("hit", "miss")]  # push excluded from the hit-rate denominator, same as index.html's own summarizePicks()

    sample_size = len(graded)
    calibration = {
        "last_updated": datetime.date.today().isoformat(),
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
        calibration["calibrated"] = True
        calibration["hit_rate"] = round(hit_rate, 3)
        calibration["deviation_pct"] = round(deviation_pct, 1)
        calibration["strong_threshold"] = round(max(3.0, DEFAULT_STRONG - nudge), 2)
        calibration["moderate_threshold"] = round(max(1.5, DEFAULT_MODERATE - nudge), 2)

    with open(OUT_PATH, "w") as f:
        json.dump(calibration, f, indent=2)

    if calibration["calibrated"]:
        print(f"Calibrated from {sample_size} graded team bets: hit rate {calibration['hit_rate']*100:.1f}% "
              f"(baseline {BASELINE_HIT_RATE*100:.0f}%) -> Strong threshold {calibration['strong_threshold']}, "
              f"Moderate threshold {calibration['moderate_threshold']}")
    else:
        print(f"Only {sample_size} graded team bets so far (need {MIN_SAMPLE_SIZE}+) -- "
              f"using original hardcoded thresholds, no calibration applied yet.")


if __name__ == "__main__":
    main()
