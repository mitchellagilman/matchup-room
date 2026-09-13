#!/usr/bin/env python3
"""
Trains a small logistic regression on this app's own graded team-bet
history to predict P(hit) from a few real features -- genuine learning
from outcomes, not just the single-number threshold nudge
calibrate_model.py does. Deliberately hand-rolled (plain gradient
descent, no scikit-learn) to avoid adding a new dependency to a project
that's stayed stdlib-only on purpose (see requirements.txt) -- with a
feature set this small, a from-scratch implementation is a few dozen
lines and easy to audit line by line.

*** WHY THIS IS SEPARATE FROM CALIBRATION, NOT A REPLACEMENT ***
calibrate_model.py adjusts ONE number (the edge threshold for "Strong")
based on ONE signal (overall hit rate). This learns WEIGHTS across
SEVERAL features (edge, favorite-vs-underdog, league) to predict hit
probability directly -- a genuinely different, more expressive kind of
model. It needs more data to trust than calibration does, precisely
because it's fitting more parameters -- a model with several free
knobs can fit 30 data points' noise perfectly and mean nothing on the
next 30. MIN_SAMPLE_SIZE here is intentionally much higher than
calibration's for exactly that reason.

*** FEATURES, AND WHY THESE THREE ***
- edge: the core existing signal (how much the model disagrees with market)
- is_favorite: whether the recommended side was the market favorite
  (negative line) or the underdog (positive line) -- both already stored
  on every existing graded pick, so this can train on the full existing
  history immediately rather than waiting for a new field to accumulate
- league_is_cfb: CFB and NFL have shown different real hit rates (see
  calibrate_model.py's per-league split) -- letting the model use league
  as a feature lets it learn that difference directly instead of via a
  separate calibration pass

Deliberately does NOT use whether SP+/SRS backed the projection yet --
that's not stored on already-graded picks, and starting the model on
only-newly-logged data would mean a much longer wait to reach
MIN_SAMPLE_SIZE. Worth adding as a feature once there's a real sample of
picks that carry it (see track_predictions.py for where that field would
need to start being stored).

Run: python3 scripts/train_model.py
Writes: data/model_weights.json
"""
import json
import math
import datetime

TRACK_PATH = "data/track-record.json"
OUT_PATH = "data/model_weights.json"
MIN_SAMPLE_SIZE = 150  # meaningfully higher than calibrate_model.py's 30 -- fitting 4 parameters (3 features + intercept) needs more evidence than adjusting 1 number does, or this just fits noise
LEARNING_RATE = 0.1
ITERATIONS = 500


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def build_features(pick):
    """Returns [edge, is_favorite, league_is_cfb] or None if a required
    field is missing (shouldn't happen for a properly-logged team bet,
    but skip rather than guess if it does)."""
    edge = pick.get("edge")
    line = pick.get("line")
    if edge is None or line is None:
        return None
    return [float(edge), 1.0 if line < 0 else 0.0, 1.0 if pick.get("league") == "CFB" else 0.0]


def standardize(X):
    """Standardizes the continuous edge column (column 0) only -- the two
    binary columns are already on a natural 0/1 scale and don't need it.
    Returns (X_scaled, mean, std) so the same transform can be re-applied
    at prediction time in index.html."""
    n = len(X)
    mean = sum(row[0] for row in X) / n
    variance = sum((row[0] - mean) ** 2 for row in X) / n
    std = math.sqrt(variance) or 1.0
    X_scaled = [[(row[0] - mean) / std, row[1], row[2]] for row in X]
    return X_scaled, mean, std


def sigmoid(z):
    if z < -60:
        return 0.0
    if z > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def train_logistic_regression(X, y):
    n = len(X)
    n_features = len(X[0])
    weights = [0.0] * n_features
    bias = 0.0
    for _ in range(ITERATIONS):
        grad_w = [0.0] * n_features
        grad_b = 0.0
        for i in range(n):
            z = bias + sum(weights[j] * X[i][j] for j in range(n_features))
            pred = sigmoid(z)
            error = pred - y[i]
            for j in range(n_features):
                grad_w[j] += error * X[i][j]
            grad_b += error
        for j in range(n_features):
            weights[j] -= LEARNING_RATE * grad_w[j] / n
        bias -= LEARNING_RATE * grad_b / n
    return weights, bias


def main():
    record = load_json(TRACK_PATH, {"picks": []})
    team_picks = [p for p in record["picks"] if p.get("type") in ("spread", "total") and p.get("status") in ("hit", "miss")]

    rows = []
    for p in team_picks:
        feats = build_features(p)
        if feats is None:
            continue
        rows.append((feats, 1.0 if p["status"] == "hit" else 0.0))

    sample_size = len(rows)
    result = {
        "last_updated": datetime.date.today().isoformat(),
        "sample_size": sample_size,
        "min_sample_size": MIN_SAMPLE_SIZE,
        "trained": False,
        "features": ["edge", "is_favorite", "league_is_cfb"],
    }

    if sample_size >= MIN_SAMPLE_SIZE:
        X = [r[0] for r in rows]
        y = [r[1] for r in rows]
        X_scaled, edge_mean, edge_std = standardize(X)
        weights, bias = train_logistic_regression(X_scaled, y)

        # Training-set accuracy -- reported plainly as training accuracy,
        # NOT held-out/out-of-sample accuracy (the sample is too small to
        # afford a real train/test split yet and still leave enough to
        # train on). This number will look optimistic; that's expected
        # and disclosed, not hidden.
        correct = 0
        for i in range(sample_size):
            z = bias + sum(weights[j] * X_scaled[i][j] for j in range(len(weights)))
            pred = 1 if sigmoid(z) >= 0.5 else 0
            if pred == y[i]:
                correct += 1
        train_accuracy = correct / sample_size

        result["trained"] = True
        result["weights"] = weights
        result["bias"] = bias
        result["edge_mean"] = edge_mean
        result["edge_std"] = edge_std
        result["train_accuracy"] = round(train_accuracy, 3)

    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    if result["trained"]:
        print(f"Trained on {sample_size} graded team bets (train accuracy {result['train_accuracy']*100:.1f}%, "
              f"not out-of-sample) -> weights {[round(w,3) for w in result['weights']]}, bias {round(result['bias'],3)}")
    else:
        print(f"Only {sample_size} graded team bets so far (need {MIN_SAMPLE_SIZE}+) -- model not trained yet, "
              f"falling back to calibrated thresholds only.")


if __name__ == "__main__":
    main()