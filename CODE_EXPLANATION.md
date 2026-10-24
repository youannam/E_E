# Code explanation

The most important files and functions, where to find them, and what to say about them. For each
module: what it does, why we need it, how it works, input/output, why this approach, and a likely
question. Read the files alongside this document; the code comments say the same things in place.

---

## ai/features.py — feature engineering

* **What**: turns one user's events of one day into 15 numbers (`FEATURE_NAMES`). Also the single
  list of event types and sensitivity levels used by the whole project.
* **Why**: a model and rules cannot reason over hundreds of raw events; they need fixed-size inputs.
* **How**: `compute_daily_features(events)` loops once over the events and increments counters
  (`download_count`, `night_login_count`, …); sets track distinct hours and resources.
  `build_feature_table(df)` does the same for many user-days (training). `validate_feature_vector`
  checks a dict before inference (all features present, numbers, not NaN, not negative).
* **In/out**: list of event dicts → dict of 15 floats.
* **Why this approach**: one shared function guarantees training and live detection use identical definitions.
* **Question**: *"Why day windows?"* — matches how analysts review behavior and gives enough events per row.

## ai/model.py — Isolation Forest

* **What**: build, train, calibrate, save, load and run the anomaly model.
* **Key functions**
  * `build_model(seed)` → `IsolationForest(n_estimators=200, random_state=seed)`.
  * `raw_scores(model, table)` → `-model.score_samples(...)` (higher = more unusual).
  * `compute_calibration(train_scores)` → `typical` (median) and `threshold` (99th percentile).
  * `normalize_score(raw, calibration)` → `50 × (raw − typical) / (threshold − typical)`, clipped to 0-100.
  * `train_model(features, seed)` → `(model, calibration)`; refuses fewer than 50 rows.
  * `save_model(...)` writes `iforest-<time>.joblib`, `<version>.json` (metadata) and `active_model.json`.
  * `load_active_model(dir)` → `AnomalyDetector` or `None` (missing model or wrong feature schema).
  * `AnomalyDetector.predict(features)` → `{is_anomaly, anomaly_score, raw_score, model_version, ...}`.
* **Why**: unsupervised (no real labels), explainable idea, fast. The calibration turns an abstract
  raw score into a scale analysts can read, without pretending it is a probability.
* **Question**: *"What if the model file is missing?"* — `load_active_model` returns `None`; the pipeline uses rules only.

## ai/train.py, ai/dataset.py, ai/evaluate.py — training and evaluation

* `dataset.generate_dataset(seed)`: 40 synthetic employees × 90 days; normal-only first 60 days; 10% of
  test-period days replaced with scenarios; returns events and labels.
* `train.run_training(seed, model_dir)`: features → time split → train → evaluate on the test period →
  save model + metrics. Run with `python -m ai.train`.
* `evaluate.classification_metrics`: precision, recall, F1, confusion matrix, false-positive rate (sklearn).
* `scripts/evaluate_detection.py`: same test set, but runs the real rule engine + risk formula too.

## simulator/ — synthetic activity

* `catalog.py`: the fictional company (departments, files with sensitivity, roles, 25 demo employees,
  including one night-shift technician).
* `generator.py`: `generate_normal_day(employee, day, rng)` builds a realistic working day; helper
  functions add suspicious pieces (`add_night_login`, `add_download_burst`, `add_sensitive_access`,
  `add_mass_deletion`, `add_usb_exfiltration`).
* `scenarios.py`: scenarios A-H; `run_scenario(id, employee, day, seed, intensity)` seeds a `random.Random`
  with (seed, scenario, user, day) so results are repeatable, and tags every event as simulated.
* `cli.py`: sends a scenario to a running API over HTTP (like an external log collector).
* **Question**: *"Do you write alerts directly in the simulator?"* — No. Simulated events go through
  `ingest_activities`, exactly like real ones.

## backend/main.py — application entry point

Creates the FastAPI app; on start-up validates settings (`JWT_SECRET_KEY` ≥ 32 characters, weights sum to 1)
and loads the model; adds CORS, security headers, a generic 500 handler (logs details, returns no stack trace)
and mounts the routers under `/api/v1`.

## backend/config.py — settings

`load_settings()` reads `.env` / environment variables into a `Settings` dataclass. `get_settings()` caches it.
`Settings.validate()` refuses insecure or inconsistent configuration.

## backend/models.py and backend/database.py — database

SQLAlchemy classes = tables (see docs/DATABASE_SCHEMA.md). `database.py` creates the engine, switches on SQLite
foreign keys, and `get_db()` gives each request its own session. Migrations are in `backend/migrations/`.

## backend/schemas.py — the API contract

Pydantic models for every request and response. Validation lives here: allowed enums (`EventType`,
`Sensitivity`, `AlertStatus`), length limits, `extra="forbid"` (unknown fields rejected), and business
checks such as "a file event needs a resource" (`ActivityCreate.check_resource_fields`) and "closing an
alert needs a note" (`AlertUpdate.check_something_changes`). `UtcDatetime` marks system times as UTC.

## backend/security.py — authentication and authorization

* `hash_password` / `verify_password`: scrypt with a random 16-byte salt; stored as
  `scrypt$n$r$p$salt$hash`; `hmac.compare_digest` for constant-time comparison.
* `create_access_token(account)`: JWT with `sub` (account id), `role`, `exp` (60 min), signed HS256.
* `get_current_account`: FastAPI dependency; decodes and checks the token and that the account is active → 401 otherwise.
* `require_roles("ADMIN")` / `require_admin` / `require_analyst_or_admin`: role checks → 403.
* `LoginRateLimiter`: 5 failures per username per 5 minutes → 429.
* **Question**: *"Why scrypt and not SHA-256?"* — SHA-256 is fast, so guessing is cheap; scrypt is deliberately
  slow and memory-hard. (The brief allowed "Argon2 or another appropriate" hash; scrypt is in Python's
  standard library, so no extra compiled dependency.)

## backend/ingestion.py — storing events

`ingest_activities(db, items)`: checks users exist (404), converts timezones and rejects future timestamps (422),
saves activities, updates devices and the user's last activity/login, commits, then calls
`analyze_days` for every affected (user, day). Used by the API, the simulator endpoint and `seed-demo`.

## backend/detection/pipeline.py — the detection pipeline

`analyze_user_day(db, user, day)` is the heart of the system:
`events → compute_daily_features → build_user_baseline → evaluate_rules → anomaly_service.score_features →
calculate_risk → save AnalysisResult → apply_alert_policy → save_profile → refresh_current_risk`.
`build_user_baseline` loads only events **before** the day (no leakage). `load_rule_settings` merges defaults
with admin changes from the database. `analyze_days` processes days oldest first.

## backend/detection/baseline.py — behavioral baseline

`compute_baseline(user_history, peer_history, known_resources)` returns a `Baseline` of type INDIVIDUAL
(≥ 7 own days), PEER_GROUP (≥ 20 department user-days) or DEFAULT, with per-feature means and standard deviations.

## backend/detection/rules.py — rule engine

* `RULES`: list of `RuleDefinition(rule_id, name, description, severity, required_fields, time_window, check)`.
* Each `check_*` function gets a `RuleContext` and returns `RuleMatch(reason, evidence, matched_event_ids)` or `None`.
* `baseline_threshold` = `max(minimum, mean + k × std)`; `count_above_baseline` is shared by the "more than usual" rules.
* `evaluate_rules(...)` runs enabled rules → `{rule_score (≤ 100), triggered_rules, matched_event_ids}`.

## backend/detection/risk.py — risk score

`calculate_risk(rule_score, ai_score, triggered_rules, settings)` → `{risk_score, risk_level, breakdown}`;
the breakdown includes the formula text shown in the UI. `risk_level(score)` maps to LOW…CRITICAL.

## backend/detection/alerts.py — alert generation and deduplication

`apply_alert_policy(...)`: below threshold → nothing new; active alert for that day → update it; closed alert
→ new alert only if `is_new_information`; otherwise create. `build_explanation` writes the plain-English text.
`find_alert_for_day` re-reads the alert from the database (`populate_existing`) so an analyst's concurrent
status change is respected (we found and fixed this case with a test).

## backend/detection/anomaly_service.py — model holder

Loads the model once (`load_detector`), returns it (`get_detector`), wraps prediction errors
(`score_features` → `OK` or `UNAVAILABLE`), and records the version in `model_versions`.

## backend/routers/*.py — endpoints

One file per area: `auth`, `users`, `activities`, `analysis` (+ model status), `alerts`, `dashboard`,
`simulator`, `rules`. Each endpoint declares its role with a dependency, e.g.
`admin: Account = Depends(require_admin)`. `alerts.update_alert` implements the investigation workflow and writes
history + audit. `common.py` has pagination (`Pagination`, `paginate`) and `get_or_404`.
`backend/serializers.py` converts rows to response models so an alert looks the same everywhere.

## backend/cli.py — setup commands

`init-db` (Alembic upgrade + default rules), `create-account`, `seed-demo` (development only: accounts with
generated passwords, 25 employees, ~30 days of history ingested through the pipeline), `export-openapi`.

## frontend/src — web dashboard

| File | What it does |
|---|---|
| `api/client.ts` | `fetch` wrapper: base URL, token header, readable errors, logout on 401 |
| `api/types.ts` | TypeScript copies of the API models |
| `api/useApi.ts` | hook: `{data, loading, error, reload}` for a GET path |
| `auth/AuthContext.tsx` | logged-in account, login/logout, session restore |
| `utils/router.ts` | hash routing (`#/alerts/12` → page + id) |
| `utils/format.ts` | dates, bytes, scores, `humanize`, query strings (unit-tested) |
| `components/RiskBreakdown.tsx` | the rules/AI/floor bar and formula |
| `components/charts/*` | SVG column chart and HTML bar chart |
| `components/ConfirmDialog.tsx` | confirmation before status/rule changes |
| `pages/*.tsx` | the 9 screens (login, overview, alerts, alert details, users, user details, activity log, simulation, rules) |

## mobile/lib — Flutter app

| File | What it does |
|---|---|
| `config.dart` | default server address (`--dart-define=API_BASE_URL=...`) |
| `api_client.dart` | HTTP calls, JSON decoding, `ApiException` (offline = status 0) |
| `models.dart` | Dart classes with `fromJson` matching the API |
| `auth_state.dart` | `ChangeNotifier` with login/logout/restore; `SecureTokenStorage` (Android Keystore) |
| `screens/guarded.dart` | logs out automatically when a request returns 401 |
| `screens/*.dart` | login, home (bottom tabs), overview, alerts, alert details (status dialog), users + risk history, profile |
| `widgets/common.dart` | risk/status chips, loading, error/offline, empty views |

## tests/

`conftest.py` sets a temporary database and model folder, trains the real model once, and provides logged-in
clients. See docs/TESTING.md for what each file covers.
