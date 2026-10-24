"""
Create the local .env file from .env.example with a freshly generated JWT secret.

    python scripts/create_env.py

It never overwrites an existing .env (delete it first if you really want a new one).
"""

import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    target = ROOT / ".env"
    if target.exists():
        print(".env already exists; leaving it unchanged.")
        return 0
    template = (ROOT / ".env.example").read_text()
    secret = secrets.token_urlsafe(48)
    content = template.replace("JWT_SECRET_KEY=\n", f"JWT_SECRET_KEY={secret}\n", 1)
    target.write_text(content)
    print("Created .env with a new random JWT_SECRET_KEY.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
