"""
Evaluation helpers. Every number here is computed from actual predictions; nothing is typed in by hand.
"""

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score


def classification_metrics(labels, predictions) -> dict:
    """Precision, recall, F1, confusion matrix and false-positive rate for binary labels (1 = suspicious)."""
    labels = np.asarray(labels, dtype=int)
    predictions = np.asarray(predictions, dtype=int)
    tn, fp, fn, tp = confusion_matrix(labels, predictions, labels=[0, 1]).ravel()
    return {
        "precision": round(float(precision_score(labels, predictions, zero_division=0)), 4),
        "recall": round(float(recall_score(labels, predictions, zero_division=0)), 4),
        "f1_score": round(float(f1_score(labels, predictions, zero_division=0)), 4),
        "false_positive_rate": round(float(fp / (fp + tn)) if (fp + tn) else 0.0, 4),
        "confusion_matrix": {"true_negative": int(tn), "false_positive": int(fp),
                             "false_negative": int(fn), "true_positive": int(tp)},
        "support": {"suspicious": int(labels.sum()), "normal": int(len(labels) - labels.sum())},
    }


def detection_rate_by_scenario(table: pd.DataFrame) -> dict:
    """Share of user-days flagged, per scenario. `table` needs columns scenario and predicted."""
    result = {}
    for scenario, group in table.groupby("scenario"):
        result[scenario] = {"days": int(len(group)), "flagged": int(group["predicted"].sum()),
                            "flag_rate": round(float(group["predicted"].mean()), 4)}
    return result


def score_distribution(scores) -> dict:
    """Diagnostics for unlabeled data: how the 0-100 anomaly scores are spread."""
    scores = np.asarray(scores, dtype=float)
    return {
        "count": int(len(scores)),
        "mean": round(float(scores.mean()), 2),
        "p50": round(float(np.percentile(scores, 50)), 2),
        "p90": round(float(np.percentile(scores, 90)), 2),
        "p99": round(float(np.percentile(scores, 99)), 2),
        "max": round(float(scores.max()), 2),
        "share_above_50": round(float((scores > 50).mean()), 4),
    }
