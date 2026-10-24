"""Tests of the real AI pipeline (training, persistence, loading, inference and score mapping)."""

import json

import numpy as np
import pytest

from ai.features import FEATURE_NAMES, FEATURE_SCHEMA_VERSION, build_feature_table, empty_features
from ai.model import ACTIVE_MODEL_FILE, AnomalyDetector, load_active_model, normalize_score, raw_scores, train_model
from ai import dataset


@pytest.fixture(scope="module")
def feature_table():
    events, labels = dataset.generate_dataset(seed=dataset.DEFAULT_SEED)
    return build_feature_table(events).merge(labels, on=["user_id", "day"])


def test_dataset_is_reproducible():
    events_a, labels_a = dataset.generate_dataset(seed=3)
    events_b, labels_b = dataset.generate_dataset(seed=3)
    assert events_a.equals(events_b) and labels_a.equals(labels_b)
    assert set(labels_a[labels_a.period == "train"].label) == {0}  # training period is normal-only


def test_training_is_reproducible(feature_table):
    train = feature_table[feature_table.period == "train"]
    model_a, calibration_a = train_model(train, seed=42)
    model_b, calibration_b = train_model(train, seed=42)
    assert calibration_a == calibration_b
    assert np.allclose(raw_scores(model_a, train.head(50)), raw_scores(model_b, train.head(50)))


def test_training_needs_enough_data(feature_table):
    with pytest.raises(ValueError):
        train_model(feature_table.head(10))


def test_score_mapping_is_documented_piecewise_linear():
    calibration = {"typical_raw_score": 0.4, "threshold_raw_score": 0.6}
    assert normalize_score(0.3, calibration) == 0
    assert normalize_score(0.4, calibration) == 0
    assert normalize_score(0.5, calibration) == 25
    assert normalize_score(0.6, calibration) == 50
    assert normalize_score(0.7, calibration) == 75
    assert normalize_score(0.95, calibration) == 100


def test_saved_model_loads_and_predicts(trained_model_dir):
    detector = load_active_model(trained_model_dir)
    assert isinstance(detector, AnomalyDetector)
    metadata = json.loads((trained_model_dir / f"{detector.version}.json").read_text())
    assert metadata["feature_schema_version"] == FEATURE_SCHEMA_VERSION
    assert metadata["feature_names"] == FEATURE_NAMES
    assert "precision" in metadata["metrics"]["test_period_ai_only"]

    result = detector.predict({**empty_features(), "total_events": 40, "login_count": 1, "file_access_count": 15,
                               "email_count": 10, "unique_active_hours": 8, "download_count": 3, "download_mb": 6,
                               "unique_resources": 8})
    assert set(result) >= {"is_anomaly", "anomaly_score", "raw_score", "model_version", "feature_schema_version"}
    assert 0 <= result["anomaly_score"] <= 100
    assert result["model_version"] == detector.version


def test_extreme_day_scores_higher_than_normal_day(trained_model_dir):
    detector = load_active_model(trained_model_dir)
    normal = {**empty_features(), "total_events": 45, "login_count": 1, "file_access_count": 16, "email_count": 10,
              "unique_active_hours": 9, "download_count": 3, "download_mb": 6, "unique_resources": 8,
              "upload_count": 2, "delete_count": 1}
    extreme = {**normal, "total_events": 140, "download_count": 60, "download_mb": 1500, "night_login_count": 1,
               "night_event_count": 70, "usb_event_count": 9, "usb_sensitive_transfer_count": 8,
               "sensitive_access_count": 20}
    assert detector.predict(extreme)["anomaly_score"] > detector.predict(normal)["anomaly_score"]
    assert detector.predict(extreme)["is_anomaly"] is True


def test_invalid_features_are_rejected(trained_model_dir):
    detector = load_active_model(trained_model_dir)
    with pytest.raises(ValueError):
        detector.predict({"total_events": 5})
    with pytest.raises(ValueError):
        detector.predict({**empty_features(), "download_count": -3})


def test_missing_model_returns_none(tmp_path):
    assert load_active_model(tmp_path) is None


def test_wrong_feature_schema_is_refused(trained_model_dir, tmp_path):
    version = json.loads((trained_model_dir / ACTIVE_MODEL_FILE).read_text())["version"]
    metadata = json.loads((trained_model_dir / f"{version}.json").read_text())
    metadata["feature_schema_version"] = "0.1"
    (tmp_path / f"{version}.json").write_text(json.dumps(metadata))
    (tmp_path / ACTIVE_MODEL_FILE).write_text(json.dumps({"version": version}))
    (tmp_path / metadata["artifact"]).write_bytes((trained_model_dir / metadata["artifact"]).read_bytes())
    assert load_active_model(tmp_path) is None
