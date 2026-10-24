# Deployment and setup (local demonstration)

Eagle Eye is prepared to run on one developer laptop. It is **not** production-ready
(see [LIMITATIONS.md](LIMITATIONS.md)).

## Requirements

| Tool | Version | Needed for |
|---|---|---|
| Python | 3.11 or newer (tested 3.13) | backend, AI, simulator, tests |
| Node.js + npm | 20 or newer (tested 22) | web dashboard |
| Flutter | 3.22 or newer + Android SDK/emulator | mobile app |
| Git | any | cloning |

## 1. Python environment

```bash
python -m venv .venv
# Linux/macOS:  source .venv/bin/activate
# Windows:      .venv\Scripts\activate
pip install -r requirements-dev.txt      # runtime + pytest, httpx, playwright
python -m playwright install chromium    # only for the browser tests
```

## 2. Configuration (.env)

```bash
python scripts/create_env.py             # copies .env.example to .env with a random JWT secret
```

| Variable | Default | Meaning |
|---|---|---|
| `ENVIRONMENT` | development | `production` disables `seed-demo` and `reset_demo.py` |
| `JWT_SECRET_KEY` | (empty) | **required**, ≥ 32 characters; the API refuses to start without it |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 60 | token lifetime |
| `DATABASE_URL` | `sqlite:///./eagle_eye.db` | any SQLAlchemy URL. The code uses only portable SQLAlchemy features, so PostgreSQL (`pip install psycopg[binary]`, `postgresql+psycopg://...`) is expected to work, but only SQLite has been tested |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | web origins allowed to call the API |
| `ORG_TIMEZONE` | Africa/Cairo | local time used for days and night hours |
| `MODEL_DIR` | `ai/models` | where trained models are saved and loaded |
| `RISK_RULE_WEIGHT`, `RISK_AI_WEIGHT` | 0.4, 0.6 | must add up to 1.0 |
| `RISK_MEDIUM_MIN`, `RISK_HIGH_MIN`, `RISK_CRITICAL_MIN` | 25, 50, 75 | level boundaries |
| `ALERT_THRESHOLD` | 50 | minimum final score for an alert |
| `DEMO_ADMIN_PASSWORD`, `DEMO_ANALYST_PASSWORD` | (empty) | development-only; random if empty |

The web dashboard has one setting, in `frontend/.env.local` (copy `frontend/.env.example`):
`VITE_API_BASE_URL=http://localhost:8000`.

## 3. Model, database and demo data

```bash
python -m ai.train                  # synthetic dataset -> model in ai/models (about 15 s)
python -m backend.cli init-db       # Alembic migrations + default rule settings
python -m backend.cli seed-demo     # DEVELOPMENT ONLY (about 45 s)
```

`seed-demo` creates the `admin` and `analyst` logins (passwords in `demo_credentials.txt`),
25 synthetic employees and about 30 days of normal history ending the day before yesterday. Every
history day goes through the real ingestion and detection pipeline. Yesterday and today are left
free for the Simulation Center.

Real accounts: `python -m backend.cli create-account <name> --role ADMIN|ANALYST` (asks for a
password of at least 10 characters).

After changing `backend/models.py`: `alembic revision --autogenerate -m "describe change"`, then
`python -m backend.cli init-db` (runs `alembic upgrade head`).

## 4. Start the components

```bash
uvicorn backend.main:app --reload                       # API on http://localhost:8000 (Swagger: /docs)
uvicorn backend.main:app --host 0.0.0.0 --port 8000     # same, reachable from phones/emulators
cd frontend && npm install && npm run dev               # dashboard on http://localhost:5173
cd frontend && npm run build && npm run preview         # production build on http://localhost:4173
                                                        #   (add http://localhost:4173 to CORS_ORIGINS)
cd mobile && flutter run                                # see mobile/README.md
```

Simulator from the command line (HTTP client, shows the external-collector path):

```bash
python -m simulator.cli --list
python -m simulator.cli --scenario COMBINED_ANOMALY --username omar.hassan --date 2026-10-09
```

## 5. Run the tests

See [TESTING.md](TESTING.md). Short version: `pytest`, `cd frontend && npm test`,
`RUN_E2E=1 pytest tests/e2e`, `cd mobile && flutter test`.

## Optional: Docker

Not provided (optional in the brief). The three commands above are enough for a local demo.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `RuntimeError: JWT_SECRET_KEY is missing...` | Run `python scripts/create_env.py` (or set the variable in `.env`) |
| Dashboard says "Cannot reach the Eagle Eye API" | API not running, or `VITE_API_BASE_URL` wrong. Check `http://localhost:8000/api/v1/health` |
| Browser console shows a CORS error | Add the dashboard's exact origin (scheme + host + port) to `CORS_ORIGINS` and restart the API |
| Overview says "AI model not loaded: rules only" | Run `python -m ai.train`, then restart the API or call `POST /api/v1/models/reload` |
| `seed-demo` says the database already contains users | Run `python scripts/reset_demo.py` (deletes and recreates the SQLite file) |
| Login returns 429 | 5 failed logins in 5 minutes for that username; wait or restart the API |
| Flutter app: "Cannot reach the Eagle Eye server" on the emulator | Use `http://10.0.2.2:8000` and start the API with `--host 0.0.0.0` |
| Flutter app on a phone cannot connect | Phone and computer on the same Wi-Fi, use the computer's IP, allow port 8000 in the firewall |
| `ModuleNotFoundError: backend` | Run commands from the project root with the virtual environment activated |
| Simulation returns "Cannot simulate a future day" | Pick today or an earlier date |
| Model loading error about the feature schema | The model was trained with older code; run `python -m ai.train` again |


## Presentation privacy note

The desktop launcher opens the dashboard in browser app mode and the UI discourages casual text copying. These are presentation measures only: they do not protect secrets from a person with access to the computer, screenshots, developer tools, process inspection, or network tools. Keep the backend behind trusted network access and rely on authentication, role authorization, and firewall rules for real protection. The phone app needs LAN access to the API when used on a physical device.
