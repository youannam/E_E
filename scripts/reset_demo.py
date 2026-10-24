"""
Development only: start the demo from a clean database (keeps the trained model).

    python scripts/reset_demo.py

Deletes the SQLite file named in DATABASE_URL, recreates the tables, and loads the demo
accounts, synthetic employees and normal history again. Use it before a presentation.
"""

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    os.chdir(ROOT)
    load_dotenv()
    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        print("Refusing to reset: ENVIRONMENT=production")
        return 1
    url = os.getenv("DATABASE_URL", "sqlite:///./eagle_eye.db")
    if not url.startswith("sqlite:///"):
        print("Only SQLite demo databases are reset automatically.")
        return 1
    database_file = Path(url.removeprefix("sqlite:///"))
    if database_file.exists():
        database_file.unlink()
        print(f"Deleted {database_file}")
    for command in (["-m", "backend.cli", "init-db"], ["-m", "backend.cli", "seed-demo"]):
        subprocess.run([sys.executable, *command], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
