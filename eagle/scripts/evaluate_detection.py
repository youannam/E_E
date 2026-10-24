"""
Evaluate the WHOLE detection system (rules + AI + risk scoring), not only the AI model.

    python -m scripts.evaluate_detection

It uses the same synthetic dataset and time-aware split as ai/train.py and the currently
active model in MODEL_DIR. For every user-day in the test period it:
  1. builds the user's baseline from their previous 30 days (never from the day itself),
  2. runs the rule engine with the default rule settings,
  3. runs the AI model,
  4. combines both with the risk formula and applies the alert policy (risk >= ALERT_THRESHOLD).
Then it reports precision, recall, F1, false-positive rate and per-scenario results for
three detectors: AI only, rules only (a rule fired), and the full system (alert raised).

The results describe synthetic data only. They are NOT real-world performance figures.
"""

import json
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from ai import dataset
from ai.evaluate import classification_metrics, detection_rate_by_scenario
from ai.features import compute_daily_features
from ai.model import load_active_model
from backend.config import get_settings
from backend.detection.baseline import compute_baseline
from backend.detection.risk import calculate_risk
from backend.detection.rule_config import BASELINE_HISTORY_DAYS, DEFAULT_RULE_SETTINGS
from backend.detection.rules import evaluate_rules

OUTPUT_FILE = Path("data/generated/system_evaluation.json")


def main():
    load_dotenv()
    settings = get_settings()
    detector = load_active_model(settings.model_dir)
    if detector is None:
        raise SystemExit("No trained model. Run: python -m ai.train")

    events, labels = dataset.generate_dataset(dataset.DEFAULT_SEED)
    roles = {employee.username: employee.job_role for employee in dataset.training_population(dataset.DEFAULT_SEED)}
    rule_settings = {rule_id: {"enabled": True, "weight": v["weight"], "parameters": v["parameters"]}
                     for rule_id, v in DEFAULT_RULE_SETTINGS.items()}

    # Group raw events by (user, day) once.
    events["timestamp"] = pd.to_datetime(events["timestamp"])
    events = events.astype(object).where(events.notna(), None)
    by_user_day: dict[tuple[str, object], list[dict]] = defaultdict(list)
    for record in events.to_dict("records"):
        record["timestamp"] = pd.Timestamp(record["timestamp"]).to_pydatetime()
        by_user_day[(record["user_id"], record["timestamp"].date())].append(record)
    features_by_user_day = {key: compute_daily_features(day_events) for key, day_events in by_user_day.items()}

    rows = []
    for label in labels[labels.period == "test"].to_dict("records"):
        user, day = label["user_id"], label["day"]
        day_events = by_user_day[(user, day)]
        history_keys = [(user, day - timedelta(days=offset)) for offset in range(1, BASELINE_HISTORY_DAYS + 1)]
        history = [features_by_user_day[key] for key in history_keys if key in features_by_user_day]
        known = {e["resource"] for key in history_keys for e in by_user_day.get(key, []) if e["resource"]}
        baseline = compute_baseline(history, [], known)

        features = features_by_user_day[(user, day)]
        rules = evaluate_rules(features, day_events, baseline, roles[user], rule_settings)
        ai = detector.predict(features)
        risk = calculate_risk(rules["rule_score"], ai["anomaly_score"], rules["triggered_rules"], settings)
        rows.append({
            "scenario": label["scenario"], "label": label["label"],
            "ai_flag": int(ai["is_anomaly"]),
            "rule_flag": int(bool(rules["triggered_rules"])),
            "alert": int(risk["risk_score"] >= settings.alert_threshold),
            "risk_score": risk["risk_score"],
        })

    table = pd.DataFrame(rows)
    report = {"note": "Synthetic data, time-aware split, model " + detector.version, "user_days": len(table)}
    for name, column in (("ai_only", "ai_flag"), ("rules_only", "rule_flag"), ("full_system_alerts", "alert")):
        report[name] = classification_metrics(table["label"], table[column])
        report[name]["by_scenario"] = detection_rate_by_scenario(table.assign(predicted=table[column]))

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(report, indent=2))
    print(f"Test user-days: {len(table)} (model {detector.version}); full report in {OUTPUT_FILE}")
    print(f"{'detector':20s} {'precision':>9s} {'recall':>7s} {'f1':>6s} {'FPR':>6s}")
    for name in ("ai_only", "rules_only", "full_system_alerts"):
        m = report[name]
        print(f"{name:20s} {m['precision']:9.3f} {m['recall']:7.3f} {m['f1_score']:6.3f} {m['false_positive_rate']:6.3f}")
    print("\nAlert rate per scenario (full system):")
    for scenario, values in report["full_system_alerts"]["by_scenario"].items():
        print(f"  {scenario:20s} {values['flagged']:3d}/{values['days']}")


if __name__ == "__main__":
    main()
