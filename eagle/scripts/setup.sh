#!/usr/bin/env bash
# Non-destructive one-time setup for Linux/macOS.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v python3 >/dev/null || { echo "Install Python 3.11+ first"; exit 1; }
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
[ -f .env ] || .venv/bin/python scripts/create_env.py
if [ ! -f eagle_eye.db ]; then
  [ -f ai/models/active_model.json ] || .venv/bin/python -m ai.train
  .venv/bin/python -c "from pathlib import Path; import re; p=Path('.env'); s=p.read_text(); s=re.sub(r'(?m)^DEMO_ADMIN_PASSWORD=.*$', 'DEMO_ADMIN_PASSWORD=EagleAdmin@2026!', s); s=re.sub(r'(?m)^DEMO_ANALYST_PASSWORD=.*$', 'DEMO_ANALYST_PASSWORD=EagleAnalyst@2026!', s); p.write_text(s)"
  .venv/bin/python -m backend.cli init-db
  .venv/bin/python -m backend.cli seed-demo --days 14
fi
echo "Setup complete. Start the web/API with RUN_WEB.bat on Windows or uvicorn backend.main:app --host 0.0.0.0 --port 8000 on Linux/macOS."
