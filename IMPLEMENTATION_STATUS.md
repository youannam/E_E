# Implementation status

Last updated: 10 October 2026. Status values:
**Tested and verified** (automated test or recorded manual check passed) ·
**Implemented but not verified** (code written, not executed in the build environment) ·
**In progress** · **Not started**.

Evidence and exact results: [docs/TESTING.md](docs/TESTING.md).

## Build environment notes

The project was built and tested in a Linux sandbox with Python 3.13 and Node.js 22 but **without
access to the npm, PyPI, pub.dev or Google download servers**. Consequences:

* Python libraries were installed from their official GitHub sources at the versions in `requirements.txt`; all Python tests ran.
* The web app was type-checked with TypeScript and bundled with esbuild (Vite unavailable), then tested in Chromium against the live API.
* The Flutter SDK could not be downloaded: the mobile code and its tests are written but **not compiled or run**.

## Checklist

### Foundation
| Requirement | Status |
|---|---|
| Project structure, git repository, .gitignore, .env.example | Tested and verified |
| Requirements files with pinned versions | Tested and verified (fresh-clone setup) |
| Setup scripts (`scripts/setup.sh`, `setup.ps1`, `create_env.py`, `reset_demo.py`) | create_env and reset_demo verified; setup.sh/ps1 implemented but not verified end to end (need package download) |

### Database (Phase 2)
| Requirement | Status |
|---|---|
| Accounts, monitored users, activities, behavioral profiles, alerts, devices, audit logs, model versions (+ analysis results, alert history, rule settings) | Tested and verified |
| Alembic migration, `init-db` | Tested and verified |
| Foreign keys and consistency rules | Tested and verified (SQLite) |
| PostgreSQL compatibility | Implemented but not verified |

### Simulator (Phase 3)
| Requirement | Status |
|---|---|
| Event types (10) | Tested and verified |
| Scenarios A-H, fixed seed, intensity | Tested and verified |
| Events enter the real pipeline (`/simulator/run`, `simulator/cli.py`, `seed-demo`) | Tested and verified |
| Simulated data labeled in UI | Tested and verified (browser test + screenshots) |
| Dataset schema documented | Done (`data/README.md`) |

### Cybersecurity rules (Phase 4)
| Requirement | Status |
|---|---|
| 8 rules with ID, name, description, enabled flag, condition, required fields, severity/weight, explanation, window, threshold | Tested and verified |
| Personal baselines with fallbacks | Tested and verified |
| Configurable thresholds and weights (DB + API + UI) | Tested and verified |
| Structured findings | Tested and verified |
| Alert deduplication | Tested and verified |
| Unit tests for each rule incl. edge cases | Tested and verified (16 tests) |

### AI (Phase 5)
| Requirement | Status |
|---|---|
| Feature engineering (15 documented features, validation) | Tested and verified |
| Baseline without future leakage | Tested and verified |
| Isolation Forest training, persistence, loading, inference, version metadata | Tested and verified |
| Safe start without a model (rules only, clearly marked) | Tested and verified |
| Deterministic 0-100 anomaly score mapping, documented | Tested and verified |
| Evaluation: precision/recall/F1/confusion matrix/FPR, time-aware split | Tested and verified (synthetic data) |
| Jupyter notebook | Code executed headless; not opened in Jupyter |

### Risk and alerts (Phase 6)
| Requirement | Status |
|---|---|
| Configurable weighted formula, levels, critical-rule floor | Tested and verified |
| Alert content (user, scores, rules, reasons, evidence, model version, status) | Tested and verified |
| Status lifecycle with history and audit; note required to close | Tested and verified |
| No automatic punishment/blocking | By design (no such code exists) |

### Backend API (Phase 7)
| Requirement | Status |
|---|---|
| All required endpoints (27 in total) | Tested and verified |
| Validation, pagination limits, safe errors, OpenAPI/Swagger, Postman-importable OpenAPI file | Tested and verified |
| CORS configuration | Tested and verified (dashboard on a different port) |

### Web dashboard (Phase 8)
| Requirement | Status |
|---|---|
| Login, overview, alerts (search/filters/sort/pagination), alert details + investigation, users, user details, activity log, simulation center, rules page | Tested and verified (browser tests + screenshot review) |
| Loading, empty, error states; confirmation dialogs; responsive layout | Tested and verified (manual + browser) |
| Unit tests | Tested and verified (7) |
| `npm install` / `vite build` with the pinned packages | Implemented but not verified |

### Flutter app (Phase 9)
| Requirement | Status |
|---|---|
| Login with server address, secure token storage | Implemented but not verified |
| Overview, alert list (status filter, refresh, load more), alert details, status changes with notes | Implemented but not verified |
| User risk list and 30-day history, profile/logout | Implemented but not verified |
| Loading, empty, offline, error states | Implemented but not verified |
| Unit and widget tests (12) | Implemented but not verified (`flutter test`) |
| Android manifest (INTERNET, cleartext for dev) | Implemented but not verified |
| Push notifications (optional) | Not started (no Firebase configuration; documented) |

### Security (Phase 10)
| Requirement | Status |
|---|---|
| scrypt password hashing, JWT with expiry, ADMIN/ANALYST roles, anonymous blocked | Tested and verified |
| Login rate limiting, input validation, audit log, safe logging, security headers | Tested and verified |
| Development-only demo account creation without committed passwords | Tested and verified |

### Testing, deployment, demo, documentation (Phases 11-14)
| Requirement | Status |
|---|---|
| Backend/AI/API tests (85) | Tested and verified |
| End-to-end acceptance scenario | Tested and verified except step 13 (Flutter) |
| Fresh-clone install following the README | Tested and verified (Python part; package download simulated) |
| Demo mode and script | Tested and verified (scenarios swept over 20 users) |
| README and all docs/ files, VIVA_PREPARATION.md, CODE_EXPLANATION.md | Done |

## Commands already run (in order)

`python -m ai.train` → `python -m backend.cli init-db` → `python -m backend.cli seed-demo` →
`pytest` (85 passed) → `python -m scripts.evaluate_detection` → `uvicorn backend.main:app` →
`python -m simulator.cli ...` → web build (tsc + esbuild) → `npm test` equivalent (7 passed) →
`RUN_E2E=1 pytest tests/e2e` (4 passed) → fresh clone: create_env, train, init-db, seed-demo, pytest (85 passed).

## Known bugs

None open. Fixed during development: an alert closed by an analyst could be overwritten by a
detection run that still held an old copy of the alert (now re-read from the database; covered by a test).

## Exact next steps for the team

1. On a normal machine: `bash scripts/setup.sh` (or `setup.ps1`) and confirm `npm run build` passes.
2. `cd mobile && flutter create --org com.eagleeye --project-name eagle_eye_mobile --platforms=android . && flutter test`,
   then `flutter run` on an emulator; fix anything the Dart analyzer reports (`flutter analyze`).
3. Rehearse `docs/DEMO_SCRIPT.md` once with all three components running.
4. Optional: Firebase push notifications, Docker Compose.
