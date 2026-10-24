# API specification

Base URL: `http://<host>:8000/api/v1`. Interactive documentation (Swagger UI) is served at
`/docs`, and the machine-readable OpenAPI file at `/openapi.json` (a copy is in
[`docs/openapi.json`](openapi.json); import it into Postman with *File > Import*).

The request/response models are defined once in `backend/schemas.py`. The web app mirrors them
in `frontend/src/api/types.ts` and the Flutter app in `mobile/lib/models.dart`.

## Conventions

* JSON in, JSON out. Field names are `snake_case`.
* **Lists** return `{"items": [...], "total": 123, "page": 1, "page_size": 20}`.
  `page` ≥ 1, `page_size` 1-100 (larger values are rejected with 422).
* **Activity times** (`timestamp`, `last_activity_at`) are local organization time without a timezone,
  e.g. `"2026-10-09T01:36:00"`. Input with a timezone is converted to `ORG_TIMEZONE`.
* **System times** (`created_at`, `updated_at`, `resolved_at`, `analyzed_at`, account `last_login`)
  are UTC with a `Z`, e.g. `"2026-10-10T15:40:16Z"`.
* **Errors** always have a `detail` field:
  * `{"detail": "Alert 99 not found"}` for 401/403/404/409/422/429 raised by the application
  * `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}` for request validation errors (422)
  * `{"detail": "Internal server error"}` for unexpected errors (500, details only in the server log)

| Status | Meaning |
|---|---|
| 200 / 201 | Success / created |
| 401 | Missing, invalid or expired token; or wrong login |
| 403 | Logged in, but the role is not allowed |
| 404 | Object does not exist |
| 409 | Duplicate (e.g. username already exists) |
| 422 | Invalid input (types, enums, missing fields, future timestamps, business rules) |
| 429 | Too many failed logins for this username (5 within 5 minutes) |

## Authentication and roles

1. `POST /auth/login` with username (or e-mail) and password.
2. Send the returned token on every other request: `Authorization: Bearer <access_token>`.
3. Tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES` (default 60); the clients then return to the login screen.

| Role | Allowed |
|---|---|
| ANALYST | every `GET` endpoint, `PATCH /alerts/{id}` |
| ADMIN | everything (adds activity ingestion, simulator runs, manual analysis, rule changes, monitored-user registration, model reload) |
| anonymous | only `POST /auth/login` and `GET /health` |

## Endpoints

| Method & path | Role | Purpose |
|---|---|---|
| `POST /auth/login` | anonymous | Log in, get a JWT |
| `GET /auth/me` | any | Current account |
| `GET /users` | analyst | Monitored users. Filters: `search`, `department`, `risk_level`; `sort` = `risk` \| `username` \| `last_activity` |
| `POST /users` | admin | Register a monitored user |
| `GET /users/{id}` | analyst | Profile, behavioral baseline and 30-day statistics |
| `GET /users/{id}/activities` | analyst | User's events, newest first (paginated) |
| `GET /users/{id}/alerts` | analyst | User's alerts (paginated) |
| `GET /users/{id}/risk-history?days=30` | analyst | Daily risk scores (1-365 days) |
| `POST /activities` | admin | Ingest one event, analyze its day |
| `POST /activities/batch` | admin | Ingest 1-2000 events, analyze each affected user-day |
| `GET /activities` | analyst | Activity log. Filters: `user_id`, `event_type`, `sensitivity`, `source`, `start`, `end`, `search` |
| `POST /analysis/run` | admin | Re-run detection for `{user_id, date}` |
| `GET /models/status` | analyst | Loaded model, features, calibration, evaluation metrics |
| `POST /models/reload` | admin | Load the newest trained model without restarting |
| `GET /alerts` | analyst | Alerts. Filters: `status`, `risk_level`, `user_id`, `date_from`, `date_to`, `search`; `sort` = `created_at` \| `risk_score` \| `window_date`; `order` = `asc` \| `desc` |
| `GET /alerts/statistics` | analyst | Counts by status and level |
| `GET /alerts/{id}` | analyst | Full alert: rules, AI result, explanation, evidence events, history, analysis |
| `PATCH /alerts/{id}` | analyst | Change status, add a note, assign/unassign yourself |
| `GET /dashboard/summary` | analyst | Headline numbers |
| `GET /dashboard/risk-distribution` | analyst | Users per current risk level |
| `GET /dashboard/alerts-over-time?days=14` | analyst | Alerts per activity day and level (1-90 days) |
| `GET /dashboard/activity-distribution?days=7` | analyst | Events per type (1-90 days) |
| `GET /simulator/scenarios` | analyst | Scenarios A-H with expected signals |
| `POST /simulator/run` | admin | Generate a scenario day and process it through the real pipeline |
| `GET /rules` | analyst | The 8 rules with current settings |
| `PATCH /rules/{rule_id}` | admin | Enable/disable, change weight or numeric thresholds or role clearances |
| `GET /health` | anonymous | `{"status": "ok", "model_loaded": true}` |

## Request and response details

### POST /auth/login

```json
{"username": "analyst", "password": "••••••••"}
```
200:
```json
{"access_token": "eyJhbGciOi...", "token_type": "bearer", "expires_in": 3600,
 "account": {"id": 2, "username": "analyst", "email": "analyst@eagle-eye.example",
             "role": "ANALYST", "is_active": true, "last_login": "2026-10-10T15:20:00Z"}}
```
401 `{"detail": "Invalid username or password"}` (same message for unknown users), 429 after 5 failures.

### POST /activities and /activities/batch

Event fields (`ActivityCreate`, unknown fields are rejected):

| Field | Type | Rules |
|---|---|---|
| `user_id` | int > 0 | must exist (404 otherwise) |
| `timestamp` | date-time | not more than 5 minutes in the future |
| `event_type` | enum | LOGIN, LOGOUT, FILE_ACCESS, FILE_DOWNLOAD, FILE_UPLOAD, FILE_DELETE, USB_CONNECT, USB_TRANSFER, EMAIL_SENT, APPLICATION_USAGE |
| `resource` | string ≤ 255 | required for FILE_* and USB_TRANSFER |
| `sensitivity` | enum | PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED; required when `resource` is set |
| `file_size_bytes` | int 0 … 50 GB | optional |
| `device_id` | string ≤ 80, letters/digits/`._:-` | optional; creates/updates the device |
| `source` | enum | API (default), IMPORT, SIMULATOR |
| `is_simulated` | bool | default false (forced true when source = SIMULATOR) |
| `details` | object | optional, ≤ ~2000 characters |

Batch body: `{"activities": [ ...1 to 2000 events... ]}`.

201 response (`IngestResponse`, shortened, real output):
```json
{"created": 1, "activity_ids": [24280],
 "analyses": [{
   "id": 551, "user_id": 2, "username": "mona.adel", "window_date": "2026-10-09", "event_count": 31,
   "features": {"total_events": 31.0, "login_count": 3.0, "night_login_count": 1.0, "...": "15 features"},
   "baseline_type": "INDIVIDUAL",
   "rule_score": 15.0,
   "triggered_rules": [{"rule_id": "UNUSUAL_LOGIN_TIME", "name": "Unusual login time", "severity": "MEDIUM",
                        "contribution": 15.0,
                        "reason": "1 login(s) between 22:00 and 06:00 (at 23:10); usual night logins per day: 0 (individual baseline)",
                        "evidence": {"night_logins": 1, "usual_night_logins_per_day": 0.0}}],
   "ai_status": "OK", "ai_is_anomaly": false, "ai_score": 46.08, "ai_raw_score": 0.583525,
   "model_version": "iforest-20261010-150901",
   "risk_score": 33.6, "risk_level": "MEDIUM",
   "score_breakdown": {"rule_score": 15.0, "ai_score": 46.08, "rule_weight": 0.4, "ai_weight": 0.6,
                       "weighted_score": 33.6, "critical_floor_applied": false,
                       "formula": "0.4 x 15 (rules) + 0.6 x 46.08 (AI) = 33.6", "ai_unavailable_reason": null},
   "alert_id": null, "analyzed_at": "2026-10-10T15:50:00Z"}]}
```

Validation error example (422):
```json
{"detail": [{"type": "value_error", "loc": ["body"],
             "msg": "Value error, resource is required for FILE_DOWNLOAD events", "...": "..."}]}
```

### GET /alerts (item = `AlertSummary`)

```json
{"id": 6, "user_id": 4, "username": "nour.samir", "department": "Engineering",
 "window_date": "2026-10-09", "created_at": "2026-10-10T15:40:16Z", "updated_at": "2026-10-10T15:41:02Z",
 "risk_score": 100.0, "risk_level": "CRITICAL", "rule_score": 100.0,
 "ai_status": "OK", "ai_score": 100.0, "ai_is_anomaly": true, "model_version": "iforest-20261010-150901",
 "status": "INVESTIGATING",
 "triggered_rule_ids": ["UNUSUAL_LOGIN_TIME", "EXCESSIVE_DOWNLOADS", "USB_SENSITIVE_TRANSFER"],
 "occurrence_count": 2, "assigned_to": null}
```

### GET /alerts/{id} (`AlertDetail`)

All `AlertSummary` fields plus: `triggered_rules` (full findings), `explanation` (text),
`resolved_at`, `resolution_notes`, `user` (`UserSummary`), `activities` (evidence events, up to
200), `history` (`[{id, action, old_status, new_status, note, actor, created_at}]`) and `analysis`
(the full `AnalysisOut` of that day, including `score_breakdown`).

### PATCH /alerts/{id}

```json
{"status": "INVESTIGATING", "note": "Calling the line manager", "assign_to_me": true}
```
At least one field is required. `status` ∈ OPEN, INVESTIGATING, RESOLVED, FALSE_POSITIVE.
Moving to RESOLVED or FALSE_POSITIVE **requires a note** (stored as `resolution_notes`).
Setting the current status again without a note → 422. Returns the updated `AlertDetail`;
the change is added to `history` and the audit log.

### POST /simulator/run

```json
{"scenario_id": "COMBINED_ANOMALY", "user_id": 1, "date": "2026-10-09", "seed": 42, "intensity": 1}
```
`date` defaults to yesterday (a complete day) and cannot be in the future; when it is today,
events later than now are skipped. `seed` 0-1,000,000, `intensity` 1-3. Response:
`{scenario_id, scenario_name, date, seed, intensity, events_created, activities[≤300], analysis, alert}`.
The events go through `ingest_activities` exactly like `POST /activities/batch`.

### PATCH /rules/{rule_id}

```json
{"enabled": true, "weight": 25, "parameters": {"minimum_count": 20}}
```
Only existing parameters can be changed; numbers must be ≥ 0; `role_clearance` values and
`default_clearance` must be sensitivity levels. Changes apply to analyses from then on.

### GET /dashboard/summary

```json
{"total_users": 25, "active_users": 25,
 "active_users_definition": "Users with at least one activity in the last 7 days",
 "open_alerts": 4, "investigating_alerts": 1, "critical_alerts": 1, "high_risk_users": 4,
 "activities_last_24h": 5, "model_loaded": true, "model_version": "iforest-20261010-150901"}
```
`critical_alerts` counts CRITICAL alerts that are OPEN or INVESTIGATING; `high_risk_users` counts
users whose current risk level is HIGH or CRITICAL.
