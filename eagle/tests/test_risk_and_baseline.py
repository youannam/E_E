from backend.config import get_settings
from backend.detection.baseline import compute_baseline
from backend.detection.risk import calculate_risk, risk_level

CRITICAL_RULE = [{"rule_id": "USB_SENSITIVE_TRANSFER", "severity": "CRITICAL"}]
MEDIUM_RULE = [{"rule_id": "UNUSUAL_LOGIN_TIME", "severity": "MEDIUM"}]


def test_weighted_formula():
    result = calculate_risk(50, 80, MEDIUM_RULE, get_settings())
    assert result["risk_score"] == 0.4 * 50 + 0.6 * 80
    assert result["risk_level"] == "HIGH"
    assert "0.4 x 50" in result["breakdown"]["formula"]


def test_ai_unavailable_uses_rules_only():
    result = calculate_risk(30, None, MEDIUM_RULE, get_settings())
    assert result["risk_score"] == 30
    assert result["breakdown"]["ai_weight"] == 0
    assert "AI unavailable" in result["breakdown"]["formula"]


def test_critical_rule_floor():
    result = calculate_risk(30, 0, CRITICAL_RULE, get_settings())
    assert result["risk_score"] == 50 and result["risk_level"] == "HIGH"
    assert result["breakdown"]["critical_floor_applied"] is True
    # No floor when the weighted score is already higher.
    assert calculate_risk(100, 90, CRITICAL_RULE, get_settings())["breakdown"]["critical_floor_applied"] is False


def test_risk_level_boundaries():
    settings = get_settings()
    assert risk_level(0, settings) == "LOW"
    assert risk_level(24.9, settings) == "LOW"
    assert risk_level(25, settings) == "MEDIUM"
    assert risk_level(49.9, settings) == "MEDIUM"
    assert risk_level(50, settings) == "HIGH"
    assert risk_level(75, settings) == "CRITICAL"
    assert risk_level(100, settings) == "CRITICAL"


def feature_row(downloads):
    from ai.features import empty_features
    return {**empty_features(), "download_count": downloads}


def test_baseline_prefers_individual_history():
    baseline = compute_baseline([feature_row(2)] * 7, [feature_row(10)] * 50, {"fs://a"})
    assert baseline.baseline_type == "INDIVIDUAL"
    assert baseline.means["download_count"] == 2
    assert baseline.known_resources == {"fs://a"}


def test_baseline_falls_back_to_peers_then_default():
    peer = compute_baseline([feature_row(2)] * 3, [feature_row(10)] * 20, {"fs://a"})
    assert peer.baseline_type == "PEER_GROUP" and peer.means["download_count"] == 10
    assert peer.known_resources == set()  # no individual history, so nothing is "known"
    default = compute_baseline([], [feature_row(10)] * 5, set())
    assert default.baseline_type == "DEFAULT" and default.observation_days == 0
