# Eagle Eye merged integration: modular backend + preserved clients

## What is integrated

- The modular FastAPI backend in `backend/` is the source of truth for authentication, SQLAlchemy models, the database, activity ingestion, baseline building, cybersecurity rules, Isolation Forest inference, risk scoring, alert creation/deduplication, simulator scenarios, and audit logging.
- The previous dark web console is preserved in `legacy_frontend/` and served by FastAPI at `/` and `/dashboard/`.
- The previous Flutter client is preserved in `mobile/` and uses the same compatibility endpoints as the web console.
- The modular API remains available under `/api/v1`; Swagger is at `/docs`.
- `backend/compat.py` translates legacy request/response shapes. It does not maintain a second database or a second detection engine.
- A legacy delete action deactivates a monitored employee rather than physically deleting rows, preserving historical activities, alerts, and foreign-key integrity.

## Why there is a compatibility layer

The old clients expect flat arrays and fields such as `file_name`, `file_sensitivity`, and `reason`. The modular API uses paginated responses and canonical fields such as `resource`, `sensitivity`, and `explanation`. The adapter translates between these contracts while both clients use the same database and detection pipeline.

## Security choices

- Login accounts are separate from monitored employees. An employee record is not an administrator or analyst login.
- Public self-registration and unauthenticated password reset are disabled because the old behavior would allow privilege abuse/account takeover. Create login accounts with `python -m backend.cli create-account <username> --role ANALYST` or `--role ADMIN`; the command prompts for a password.
- Only ADMIN accounts can add/edit/deactivate monitored employees or change alert status from the legacy clients. Analyst read/investigation access remains controlled by the canonical API's role policy.
- JWT secrets are generated into local `.env`; do not share `.env` or use demo passwords outside the local demonstration.
- The included synthetic alert is generated through the real `/api/v1/simulator/run` pipeline, not manually inserted into the alerts table.

## Verification performed

- The project test suite reported **88 passed**, including four compatibility smoke/security tests.
- Verified login, dashboard statistics, user/alert/activity lists, static web assets, `/api/v1/health`, `/api/v1/dashboard/summary`, model status, admin-only monitored-user CRUD, and rejection of public registration/password reset.
- A trained Isolation Forest model artifact is included in `ai/models/`; evaluation uses synthetic held-out data only. Model scores are not proof of malicious intent.
- Flutter compilation could not be run in the build environment because Flutter SDK was not installed there. Run `RUN_MOBILE.bat` on the target Windows machine after Flutter and Android SDK are configured.

## Run commands

- Web and API: `RUN_WEB.bat`
- Mobile: `RUN_MOBILE.bat`

Both launchers create `.env` and the Python virtual environment when missing. They do not overwrite an existing database. For a new/empty database, they initialize the schema and seed synthetic demo data.
