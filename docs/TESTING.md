# Testing

Status words used here: **PASS** (run and passed), **FAIL** (run and failed), **NOT RUN**
(could not be run; the reason is given).

Last verified run: 10 October 2026, Linux, Python 3.13.16, Node.js 22.22.0, Chromium 141
(Playwright 1.56). Results below are copied from that run, not estimated.

## Summary

| Suite | Command | Tests | Result |
|---|---|---|---|
| Backend, AI, simulator, API integration, end-to-end API scenario + legacy-client compatibility | `pytest` | 88 | **PASS** (88 passed reported) |
| Same suite in a fresh `git clone` after following the README | `pytest` | 85 | **PASS** |
| Whole-system evaluation | `python -m scripts.evaluate_detection` | – | **PASS** (runs; numbers in AI_METHODOLOGY.md) |
| Notebook code (all cells executed headless) | see below | – | **PASS** |
| Frontend type check | `npm run typecheck` (tsc) | – | **PASS** (TypeScript 6.0.3; package.json pins 5.9) |
| Frontend unit tests | `npm test` | 7 | **PASS** |
| Frontend production bundle | `npm run build` | – | **PASS with esbuild**, NOT RUN with Vite (see note) |
| Web dashboard browser tests against the live API | `RUN_E2E=1 pytest tests/e2e -v` | 4 | **PASS** |
| Flutter unit + widget tests | `flutter test` | 12 | **NOT RUN**: Flutter SDK unavailable in the build environment |
| Flutter app on emulator/phone | `flutter run` | – | **NOT RUN**: same reason |

**Why some items were NOT RUN.** The environment used to build the project had no access to the
npm, PyPI, pub.dev or Google storage download servers. Python libraries were installed from their
official GitHub sources at the exact versions in `requirements.txt`. For the web app, React and
TypeScript were available locally but Vite was not, so the same source files were type-checked
with `tsc` and bundled with esbuild (the bundler Vite itself uses in development) and then tested
in Chromium against the real API. The Flutter SDK could not be downloaded, so the Dart code and
tests have not been compiled or executed yet. Run these on a normal machine:

```bash
cd frontend && npm install && npm run build && npm test
cd mobile && flutter create --org com.eagleeye --project-name eagle_eye_mobile --platforms=android . && flutter pub get && flutter test
```

## What each Python test file covers

| File | Tests | Covers |
|---|---|---|
| `tests/test_features.py` | 6 | feature counts, night logins, empty days, missing values, feature table, input validation (missing/negative/NaN/non-number) |
| `tests/test_rules.py` | 16 | every rule triggered and not triggered, value exactly at threshold, night-shift baseline, personal thresholds, unknown role, rule 7 only with individual history, disabled rule, configurable threshold, 100-point cap |
| `tests/test_risk_and_baseline.py` | 6 | weighted formula, AI unavailable, critical floor, level boundaries, INDIVIDUAL/PEER/DEFAULT baseline selection |
| `tests/test_ai_model.py` | 9 | dataset reproducibility, training reproducibility, too little data, score mapping, save/load/predict schema and version metadata, extreme vs normal day, invalid features, missing model, wrong feature schema refused |
| `tests/test_simulator.py` | 13 | seed reproducibility, every scenario valid and labeled simulated, combined anomaly signals, intensity, invalid input, demo employees |
| `tests/test_api_auth.py` | 12 | password hashing, login success without secrets, login by e-mail, same error for wrong password and unknown user, validation, rate limit (429), token checks (401), anonymous access blocked, analyst blocked from admin actions (403), audit of logins, pagination limit, security headers |
| `tests/test_api_activities.py` | 6 | single + batch ingestion with analysis, validation errors, future timestamps, unknown users, timezone conversion, activity filters |
| `tests/test_api_alerts.py` | 7 | explainable alert from combined anomaly, no alert for a normal day, deduplication of a burst, closed alert not re-raised without new information but re-raised with it, status workflow + history + audit, update validation, filters and statistics |
| `tests/test_api_other.py` | 9 | users endpoints, creating monitored users, simulator through the real pipeline, simulator validation, dashboard numbers, rule configuration, disabled rule respected by pipeline, model status + manual analysis, rules-only mode when the model is missing |
| `tests/test_end_to_end.py` | 1 | the 15-step acceptance scenario of the specification through the HTTP API |
| `tests/test_legacy_ui_integration.py` | 4 | old web assets, compatibility API shapes, admin-only employee management, disabled unsafe self-registration/reset |

The tests use a temporary SQLite database and train the **real** Isolation Forest once per run;
nothing is mocked in the detection pipeline.

## End-to-end acceptance scenario (specification section 16)

| Step | Evidence | Status |
|---|---|---|
| 1 Clean database | test fixture drops/creates tables; fresh clone used a new file | PASS |
| 2 Demo accounts and synthetic users | fixture / `seed-demo` | PASS |
| 3 Train or load the real model | `run_training` in tests; `python -m ai.train` in the clone | PASS |
| 4-6 Normal activity for a new user does not create an unjustified critical alert | `test_full_detection_workflow` (DEFAULT baseline, no alert) | PASS |
| 7 Combined suspicious scenario | same test + browser test | PASS |
| 8 Rules execute | ≥ 3 triggered rules asserted | PASS |
| 9 AI model executes | `ai_status = OK`, model version and score asserted | PASS |
| 10 Combined score calculated | weighted score recomputed and compared | PASS |
| 11 Alert persisted | `analysis_results.alert_id` and `GET /alerts/{id}` | PASS |
| 12 Web dashboard retrieves the alert | `tests/e2e` opens it in Chromium | PASS |
| 13 Flutter retrieves the same alert | widget test with a fake backend written; real device run | NOT RUN (no Flutter SDK) |
| 14 Change alert status | API test + browser test (with confirmation dialog) | PASS |
| 15 Change persists and is visible to clients | re-read via API and in the filtered alert list | PASS |

## Browser tests (tests/e2e/test_web_dashboard.py)

1. Wrong password shows the server's error message.
2. Dashboard numbers equal `GET /dashboard/summary`; no JavaScript errors.
3. Simulation center runs the combined scenario through the real pipeline, the result links to an
   alert that the API confirms (AI status OK, rules triggered), the alert page opens, "Start
   investigating" is confirmed in the dialog and persists in the API, a note is added, and the alert
   appears when filtering by INVESTIGATING.
4. An analyst sees the simulation button disabled.

Requires the API (`uvicorn backend.main:app`) and the dashboard (`npm run dev`) to be running with
the demo data. They modify the demo database (a simulated day and an alert status).

## Notebook check

All code cells of `ai/notebooks/model_evaluation.ipynb` were executed in order with a headless
matplotlib backend (`plt.show()` replaced by saving the figure); they ran without errors.

## Manual checks done

* Screenshots of every web page at 1440 px and 390 px width were reviewed (no horizontal scrolling
  at phone width, readable charts, risk colors consistent).
* `python -m simulator.cli` sent a scenario over HTTP to a running API and received the analysis.
