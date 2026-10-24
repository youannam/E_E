"""
Behavioral baseline: "what does a normal day look like for this user?"

For each feature (download_count, delete_count, ...) we keep the mean (average) and the
standard deviation (how much it usually varies) over the user's previous days.

Which history is used, in order of preference:
  1. INDIVIDUAL - the user's own last 30 days, if they were active on at least 7 of them.
  2. PEER_GROUP - all users of the same department, if the user lacks history.
  3. DEFAULT    - documented fallback numbers (rule_config.py) when even peers lack history.

Only days BEFORE the analyzed day are used. Using the analyzed day itself (or later days)
would let the suspicious activity raise its own baseline and hide itself; that is the
"future information leakage" the specification warns about.
"""

from dataclasses import dataclass, field
from datetime import date

import numpy as np

from ai.features import FEATURE_NAMES
from backend.detection.rule_config import (
    DEFAULT_BASELINE_MEANS,
    DEFAULT_BASELINE_STDS,
    MIN_INDIVIDUAL_DAYS,
    MIN_PEER_USER_DAYS,
)


@dataclass
class Baseline:
    baseline_type: str  # INDIVIDUAL, PEER_GROUP or DEFAULT
    observation_days: int
    means: dict[str, float]
    stds: dict[str, float]
    known_resources: set[str] = field(default_factory=set)  # only filled for INDIVIDUAL baselines
    window_start: date | None = None
    window_end: date | None = None

    @property
    def is_individual(self) -> bool:
        return self.baseline_type == "INDIVIDUAL"


def summarize(feature_rows: list[dict]) -> tuple[dict, dict]:
    """Mean and standard deviation of every feature across the given days."""
    means, stds = {}, {}
    for name in FEATURE_NAMES:
        values = np.array([row[name] for row in feature_rows], dtype=float)
        means[name] = round(float(values.mean()), 3)
        stds[name] = round(float(values.std()), 3)
    return means, stds


def compute_baseline(
    user_history: list[dict],
    peer_history: list[dict],
    known_resources: set[str],
    window_start: date | None = None,
    window_end: date | None = None,
) -> Baseline:
    """
    user_history: feature dicts of the user's previous active days
    peer_history: feature dicts of previous active days of other users in the same department
    known_resources: resources the user touched in the history window
    """
    if len(user_history) >= MIN_INDIVIDUAL_DAYS:
        means, stds = summarize(user_history)
        return Baseline("INDIVIDUAL", len(user_history), means, stds, set(known_resources), window_start, window_end)

    if len(peer_history) >= MIN_PEER_USER_DAYS:
        means, stds = summarize(peer_history)
        return Baseline("PEER_GROUP", len(peer_history), means, stds, set(), window_start, window_end)

    return Baseline("DEFAULT", 0, dict(DEFAULT_BASELINE_MEANS), dict(DEFAULT_BASELINE_STDS), set(), window_start, window_end)
