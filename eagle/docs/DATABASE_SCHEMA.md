# Database schema

Defined in `backend/models.py`; created by the Alembic migration in
`backend/migrations/versions/` (`python -m backend.cli init-db`).

## ER diagram

```mermaid
erDiagram
  ACCOUNTS ||--o{ ALERT_HISTORY : "acts in"
  ACCOUNTS ||--o{ ALERTS : "assigned"
  MONITORED_USERS ||--o{ ACTIVITIES : performs
  MONITORED_USERS ||--o{ DEVICES : uses
  MONITORED_USERS ||--o| BEHAVIORAL_PROFILES : "has baseline"
  MONITORED_USERS ||--o{ ANALYSIS_RESULTS : "risk per day"
  MONITORED_USERS ||--o{ ALERTS : "subject of"
  ALERTS ||--o{ ALERT_HISTORY : records
  ALERTS }o--o{ ACTIVITIES : "evidence (alert_activities)"
  ANALYSIS_RESULTS }o--o| ALERTS : "covered by"

  ACCOUNTS { int id PK
    string username UK
    string email UK
    string password_hash
    string role
    bool is_active
    datetime created_at
    datetime last_login }
  MONITORED_USERS { int id PK
    string username UK
    string email
    string department
    string job_role
    string status
    bool is_synthetic
    datetime last_login
    datetime last_activity_at
    float current_risk_score
    string current_risk_level }
  ACTIVITIES { int id PK
    int user_id FK
    datetime timestamp
    string event_type
    string resource
    string sensitivity
    int file_size_bytes
    string device_id
    string source
    bool is_simulated
    json details }
  DEVICES { int id PK
    string device_id UK
    int user_id FK
    string device_type
    string status
    datetime last_seen }
  BEHAVIORAL_PROFILES { int id PK
    int user_id FK
    string baseline_type
    date window_start
    date window_end
    int observation_days
    json feature_means
    json feature_stds }
  ANALYSIS_RESULTS { int id PK
    int user_id FK
    date window_date
    json features
    float rule_score
    json triggered_rules
    string ai_status
    float ai_score
    float risk_score
    string risk_level
    json score_breakdown
    int alert_id FK }
  ALERTS { int id PK
    int user_id FK
    date window_date
    float risk_score
    string risk_level
    float rule_score
    float ai_score
    bool ai_is_anomaly
    string model_version
    json triggered_rules
    text explanation
    string status
    int occurrence_count
    int assigned_to_id FK
    datetime resolved_at
    text resolution_notes }
  ALERT_HISTORY { int id PK
    int alert_id FK
    int account_id FK
    string action
    string old_status
    string new_status
    text note }
```

Not drawn: `audit_logs` (actor, action, entity, details, time), `rule_settings` (rule_id,
enabled, weight, parameters) and `model_versions` (version, algorithm, training dataset,
trained_at, feature schema version, metrics, artifact path, status). They have no foreign keys.

## Tables

| Table | One row is | Notes |
|---|---|---|
| `accounts` | A login of Eagle Eye (ADMIN or ANALYST) | Only table with password hashes (scrypt) |
| `monitored_users` | A (synthetic) employee being monitored | No password; `current_risk_*` = highest daily risk in the last 7 days |
| `activities` | One event | Indexed by user, timestamp, event type. `is_simulated` marks simulator data |
| `devices` | A workstation or USB device seen in events | Created automatically during ingestion |
| `behavioral_profiles` | The latest baseline of a user | Updated in place after each analysis |
| `analysis_results` | Detection result for one user-day | Unique (user_id, window_date): re-analysis updates the row. This is the risk history |
| `alerts` | An alert for one user-day | At most one active alert per user-day (deduplication) |
| `alert_activities` | Link alert ↔ evidence activity | Many-to-many, cascade on delete |
| `alert_history` | One change to an alert | CREATED, UPDATED_BY_DETECTION, STATUS_CHANGED, NOTE_ADDED, ASSIGNED, UNASSIGNED |
| `audit_logs` | One action in Eagle Eye | LOGIN, LOGIN_FAILED, ACTIVITIES_INGESTED, SIMULATION_RUN, RULE_UPDATED, ALERT_UPDATED, ... |
| `rule_settings` | Configuration of one rule | Seeded from `backend/detection/rule_config.py` |
| `model_versions` | A trained model that was loaded | Older versions are marked RETIRED |

## Consistency rules

* Activities and alerts reference users with `ON DELETE RESTRICT`: a user with history cannot be
  deleted by accident (users are deactivated with `status`, not deleted).
* Profiles and analysis results cascade with the user; alert history and evidence links cascade
  with the alert.
* SQLite enforces foreign keys because `backend/database.py` switches them on for every connection.
* Stored JSON (features, rules, breakdown) is a snapshot of the analysis at that moment, so an
  alert still explains itself even if rule settings change later.

## Sensitive data

No message contents, keystrokes or personal data beyond a username, department, role and an
optional work e-mail are stored for monitored users. Passwords exist only as scrypt hashes for
Eagle Eye accounts. Tokens are never stored on the server.
