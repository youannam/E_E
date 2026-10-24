"""
Keeps the trained AI model in memory for the backend.

The model is loaded once (at startup, or when an admin reloads it), not trained on
every request. If no model has been trained yet, `get_detector()` returns None and the
pipeline continues with rules only, marking the AI part as UNAVAILABLE.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.model import AnomalyDetector, load_active_model
from backend.config import get_settings
from backend.models import ModelVersion

logger = logging.getLogger(__name__)

_detector: AnomalyDetector | None = None
_loaded = False


def load_detector() -> AnomalyDetector | None:
    global _detector, _loaded
    _detector = load_active_model(get_settings().model_dir)
    _loaded = True
    if _detector:
        logger.info("AI model %s loaded", _detector.version)
    return _detector


def get_detector() -> AnomalyDetector | None:
    if not _loaded:
        load_detector()
    return _detector


def score_features(features: dict) -> dict:
    """
    Run the model on one feature vector.
    Returns {"status": "OK", ...model output...} or {"status": "UNAVAILABLE", "reason": ...}.
    """
    detector = get_detector()
    if detector is None:
        return {"status": "UNAVAILABLE", "reason": "No trained model is loaded. Run: python -m ai.train"}
    try:
        return {"status": "OK", **detector.predict(features)}
    except ValueError as error:
        logger.error("Invalid features for the AI model: %s", error)
        return {"status": "UNAVAILABLE", "reason": f"Invalid features: {error}"}


def register_model_version(db: Session) -> None:
    """Record the loaded model in the model_versions table (once per version)."""
    detector = get_detector()
    if detector is None:
        return
    existing = db.scalar(select(ModelVersion).where(ModelVersion.version == detector.version))
    if existing:
        return
    for older in db.scalars(select(ModelVersion).where(ModelVersion.status == "ACTIVE")):
        older.status = "RETIRED"
    meta = detector.metadata
    db.add(ModelVersion(
        version=detector.version,
        algorithm=meta.get("algorithm", "IsolationForest"),
        training_dataset=meta.get("training_dataset", {}),
        trained_at=meta.get("trained_at", ""),
        feature_schema_version=meta["feature_schema_version"],
        metrics=meta.get("metrics", {}),
        artifact_path=f"{get_settings().model_dir}/{meta.get('artifact', '')}",
        status="ACTIVE",
    ))
    db.commit()
