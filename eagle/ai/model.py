"""
Isolation Forest anomaly model: training, score normalization, saving, loading and inference.

How Isolation Forest works (short version, see docs/AI_METHODOLOGY.md for more):
  The model builds many random decision trees. Each tree keeps splitting the data on a
  random feature at a random value until every point is alone. Unusual points (for
  example a day with 80 downloads when normal days have 2-5) get separated after only
  a few splits, so they have a SHORT average path length. Normal points need many splits.
  scikit-learn turns the average path length into a score.

Score vocabulary used in this project (kept separate on purpose):
  raw_score         = -model.score_samples(x). Higher = more unusual. About 0.45 for a
                      typical day, approaching 1.0 for extremely isolated points.
  anomaly_score     = raw_score mapped to 0-100 with the documented mapping below.
                      It is NOT a probability of malicious behavior.
  is_anomaly        = raw_score above the threshold learned from training data.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from ai.features import FEATURE_NAMES, FEATURE_SCHEMA_VERSION, validate_feature_vector

logger = logging.getLogger(__name__)

ACTIVE_MODEL_FILE = "active_model.json"
N_ESTIMATORS = 200
# The anomaly threshold is the 99th percentile of raw scores on (normal) training days:
# about 1 in 100 ordinary days is expected to be flagged. That is an explicit, tunable choice.
THRESHOLD_PERCENTILE = 99.0


def build_model(seed: int) -> IsolationForest:
    """
    contamination="auto" only affects scikit-learn's own predict(); we do not use predict().
    Our anomaly threshold is learned from the training scores (see compute_calibration).
    Isolation Forest splits each feature at random values between its min and max, so it
    does not need feature scaling. We tried a log transform of the counts; on our synthetic
    test period it lowered recall, so the raw daily counts are used (see docs/AI_METHODOLOGY.md).
    """
    return IsolationForest(n_estimators=N_ESTIMATORS, contamination="auto", random_state=seed)


def raw_scores(model: IsolationForest, feature_table: pd.DataFrame) -> np.ndarray:
    """Higher = more unusual. (scikit-learn's score_samples is the opposite, so we negate it.)"""
    return -model.score_samples(feature_table[FEATURE_NAMES])


def compute_calibration(training_raw_scores: np.ndarray) -> dict:
    """
    Two anchor points for turning raw scores into the 0-100 anomaly score.
    Both come from the training (normal) data, so they describe "normal" for this model.
    """
    typical = float(np.median(training_raw_scores))
    threshold = float(np.percentile(training_raw_scores, THRESHOLD_PERCENTILE))
    return {
        "typical_raw_score": round(typical, 6),
        "threshold_raw_score": round(threshold, 6),
        "threshold_percentile": THRESHOLD_PERCENTILE,
    }


def normalize_score(raw_score: float, calibration: dict) -> float:
    """
    Linear mapping, clipped to 0..100 (deterministic and easy to explain):

        anomaly_score = 50 * (raw - typical) / (threshold - typical)

        raw <= typical day           -> 0
        raw == threshold             -> 50  (the model's anomaly boundary)
        twice as far past typical    -> 100 (capped)

    So an anomaly_score above 50 means exactly "flagged as anomalous by the model".
    """
    typical = calibration["typical_raw_score"]
    threshold = calibration["threshold_raw_score"]
    spread = max(threshold - typical, 1e-6)
    score = 50 * (raw_score - typical) / spread
    return round(min(100.0, max(0.0, score)), 2)


def train_model(training_features: pd.DataFrame, seed: int = 42) -> tuple[IsolationForest, dict]:
    """Fit the model on normal user-days and learn the score calibration."""
    if len(training_features) < 50:
        raise ValueError("At least 50 user-days are needed to train a meaningful model")
    model = build_model(seed)
    model.fit(training_features[FEATURE_NAMES])
    calibration = compute_calibration(raw_scores(model, training_features))
    return model, calibration


def save_model(model: IsolationForest, metadata: dict, model_dir: str | Path) -> Path:
    """Save the model file + a metadata JSON, and mark this version as the active one."""
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    version = metadata["version"]
    model_path = model_dir / f"{version}.joblib"
    joblib.dump(model, model_path)
    metadata = {**metadata, "artifact": model_path.name}
    (model_dir / f"{version}.json").write_text(json.dumps(metadata, indent=2, default=str))
    (model_dir / ACTIVE_MODEL_FILE).write_text(json.dumps({"version": version}, indent=2))
    return model_path


def new_version_name() -> str:
    return "iforest-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


class AnomalyDetector:
    """A loaded model ready for inference. Created by load_active_model()."""

    def __init__(self, model: IsolationForest, metadata: dict):
        self.model = model
        self.metadata = metadata
        self.version = metadata["version"]
        self.calibration = metadata["calibration"]

    def predict(self, features: dict) -> dict:
        """
        Score one user-day. Input: the dict from ai.features.compute_daily_features.
        Raises ValueError if the features are invalid (missing, negative, NaN, ...).
        """
        values = validate_feature_vector(features)
        row = pd.DataFrame([values], columns=FEATURE_NAMES)
        raw = float(raw_scores(self.model, row)[0])
        score = normalize_score(raw, self.calibration)
        return {
            "is_anomaly": raw > self.calibration["threshold_raw_score"],
            "anomaly_score": score,
            "raw_score": round(raw, 6),
            "model_version": self.version,
            "feature_schema_version": self.metadata["feature_schema_version"],
            "threshold_raw_score": self.calibration["threshold_raw_score"],
        }


def load_active_model(model_dir: str | Path) -> AnomalyDetector | None:
    """
    Load the model marked active in model_dir. Returns None (and logs why) if there is no
    trained model or it cannot be used. The backend keeps running without AI in that case.
    """
    model_dir = Path(model_dir)
    pointer = model_dir / ACTIVE_MODEL_FILE
    if not pointer.exists():
        logger.warning("No trained model found in %s. Run: python -m ai.train", model_dir)
        return None
    try:
        version = json.loads(pointer.read_text())["version"]
        metadata = json.loads((model_dir / f"{version}.json").read_text())
        if metadata.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
            logger.error("Model %s uses feature schema %s but the code uses %s. Retrain with: python -m ai.train",
                         version, metadata.get("feature_schema_version"), FEATURE_SCHEMA_VERSION)
            return None
        model = joblib.load(model_dir / metadata["artifact"])
        return AnomalyDetector(model, metadata)
    except Exception:
        logger.exception("Could not load the model from %s", model_dir)
        return None
