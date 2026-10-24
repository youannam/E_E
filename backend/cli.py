"""
Command-line tools for setting up Eagle Eye. Run from the project root:

    python -m backend.cli init-db            create/upgrade the database tables (Alembic migrations)
    python -m backend.cli create-account     create an ADMIN or ANALYST login (asks for the password)
    python -m backend.cli seed-demo          DEVELOPMENT ONLY: demo logins + synthetic employees + history
    python -m backend.cli export-openapi     write docs/openapi.json (import it into Postman)
"""

import argparse
import getpass
import json
import os
import random
import secrets
import sys
from datetime import timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from backend.config import get_settings
from backend.database import SessionLocal
from backend.detection import anomaly_service
from backend.detection.rule_config import DEFAULT_RULE_SETTINGS
from backend.ingestion import ingest_activities
from backend.models import Account, MonitoredUser, RuleSetting
from backend.schemas import ActivityCreate
from backend.security import MIN_PASSWORD_LENGTH, hash_password
from backend.timeutils import org_today
from simulator.catalog import DEMO_EMPLOYEES, WEEKEND_DAYS, find_demo_employee
from simulator.generator import generate_normal_day
from simulator.scenarios import SCENARIOS, run_scenario

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_FILE = PROJECT_ROOT / "demo_credentials.txt"


def init_db() -> None:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "backend" / "migrations"))
    command.upgrade(config, "head")
    with SessionLocal() as db:
        for rule_id, values in DEFAULT_RULE_SETTINGS.items():
            if db.get(RuleSetting, rule_id) is None:
                db.add(RuleSetting(rule_id=rule_id, enabled=True, weight=values["weight"],
                                   parameters=values["parameters"]))
        db.commit()
    print("Database is up to date and default rule settings are in place.")


def create_account(username: str, role: str, password: str, email: str | None = None) -> Account:
    with SessionLocal() as db:
        if db.scalar(select(Account).where(Account.username == username)):
            raise SystemExit(f"Account '{username}' already exists")
        account = Account(username=username, email=email, role=role, password_hash=hash_password(password))
        db.add(account)
        db.commit()
        return account


def create_account_command(args) -> None:
    password = getpass.getpass(f"Password for {args.username} (min {MIN_PASSWORD_LENGTH} characters): ")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match")
    create_account(args.username, args.role, password, args.email)
    print(f"Created {args.role} account '{args.username}'.")


def seed_demo(history_days: int, seed: int) -> None:
    """
    Development-only demo data. Everything goes through the normal ingestion + detection
    pipeline; no alert or score is written directly.
    History covers the days up to the day before yesterday, leaving yesterday and today free
    for the Simulation Center.
    """
    settings = get_settings()
    if settings.is_production:
        raise SystemExit("seed-demo is disabled when ENVIRONMENT=production")

    with SessionLocal() as db:
        if db.scalar(select(MonitoredUser).limit(1)):
            raise SystemExit("The database already contains users. Delete eagle_eye.db and run init-db first.")

    # 1. Demo logins (passwords from .env, or random ones written to demo_credentials.txt)
    lines = ["Eagle Eye DEVELOPMENT-ONLY demo credentials. Do not use these anywhere else.", ""]
    for username, role, env_name in (("admin", "ADMIN", "DEMO_ADMIN_PASSWORD"),
                                     ("analyst", "ANALYST", "DEMO_ANALYST_PASSWORD")):
        password = os.getenv(env_name) or secrets.token_urlsafe(12)
        create_account(username, role, password, f"{username}@eagle-eye.example")
        lines.append(f"{role:8s} username: {username:8s} password: {password}")
    CREDENTIALS_FILE.write_text("\n".join(lines) + "\n")
    print(f"Created demo accounts 'admin' and 'analyst'. Passwords saved in {CREDENTIALS_FILE.name} (git-ignored).")

    # 2. Synthetic employees
    with SessionLocal() as db:
        for employee in DEMO_EMPLOYEES:
            db.add(MonitoredUser(username=employee.username, email=f"{employee.username}@corp.example",
                                 department=employee.department, job_role=employee.job_role, is_synthetic=True))
        db.commit()
        user_ids = {user.username: user.id for user in db.scalars(select(MonitoredUser))}

    # 3. Normal history, one day at a time (older days first, so baselines build up as in real life)
    if anomaly_service.get_detector() is None:
        print("Warning: no AI model found; history will be analyzed with rules only. Run: python -m ai.train")
    rng = random.Random(seed)
    last_day = org_today() - timedelta(days=2)
    days = [last_day - timedelta(days=offset) for offset in range(history_days - 1, -1, -1)]
    working_days = [day for day in days if day.weekday() not in WEEKEND_DAYS]
    with SessionLocal() as db:
        for number, day in enumerate(working_days, start=1):
            items = []
            for employee in DEMO_EMPLOYEES:
                for event in generate_normal_day(employee, day, rng):
                    items.append(ActivityCreate(user_id=user_ids[employee.username], source="SIMULATOR",
                                                is_simulated=True, **{**event, "details": {**event["details"],
                                                                                          "scenario": "SEED_HISTORY"}}))
            ingest_activities(db, items)
            print(f"  history day {number}/{len(working_days)}: {day} ({len(items)} events)", flush=True)
        anomaly_service.register_model_version(db)

    # 4. Seed a small set of suspicious examples on yesterday, after the normal history.
    # Every example goes through normal ingestion/detection; alerts are never inserted by hand.
    example_day = org_today() - timedelta(days=1)
    # Seed three high-signal cases for a reliable first-launch demonstration. Each is
    # generated for a different employee and still goes through the real detection pipeline.
    # The Detection Lab lets the presenter create additional scenarios on demand.
    example_plan = [
        ("COMBINED_ANOMALY", DEMO_EMPLOYEES[0], 2, seed + 101),   # Engineering
        ("COMBINED_ANOMALY", DEMO_EMPLOYEES[5], 2, seed + 202),   # Finance
        ("COMBINED_ANOMALY", DEMO_EMPLOYEES[12], 2, seed + 303),  # Sales
    ]
    with SessionLocal() as db:
        user_ids = {user.username: user.id for user in db.scalars(select(MonitoredUser))}
        for scenario_id, employee, intensity, scenario_seed in example_plan:
            user_id = user_ids.get(employee.username)
            if not user_id:
                continue
            generated = run_scenario(scenario_id, employee, example_day, seed=scenario_seed, intensity=intensity)
            items = [ActivityCreate(user_id=user_id, source="SIMULATOR", is_simulated=True,
                                    **{**event, "details": {**event.get("details", {}),
                                                              "scenario": scenario_id,
                                                              "demo_seed": True}})
                     for event in generated]
            try:
                ingest_activities(db, items)
            except Exception as exc:
                db.rollback()
                print(f"Warning: could not seed demo scenario {scenario_id}: {exc}", flush=True)
                continue
            db.commit()
            print(f"  demo example ready: {scenario_id} / {employee.username}", flush=True)
        anomaly_service.register_model_version(db)
    print("Demo data ready: normal history plus suspicious example scenarios. Start the API with: uvicorn backend.main:app --reload")


def export_openapi() -> None:
    from backend.main import app

    path = PROJECT_ROOT / "docs" / "openapi.json"
    path.write_text(json.dumps(app.openapi(), indent=2))
    print(f"Wrote {path}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="python -m backend.cli", description="Eagle Eye setup commands")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("init-db", help="create or upgrade the database")
    account_parser = subcommands.add_parser("create-account", help="create a login account")
    account_parser.add_argument("username")
    account_parser.add_argument("--role", choices=["ADMIN", "ANALYST"], default="ANALYST")
    account_parser.add_argument("--email")
    seed_parser = subcommands.add_parser("seed-demo", help="development-only demo data")
    seed_parser.add_argument("--days", type=int, default=30, help="calendar days of normal history")
    seed_parser.add_argument("--seed", type=int, default=2026)
    subcommands.add_parser("export-openapi", help="write docs/openapi.json")
    args = parser.parse_args(argv)

    if args.command == "init-db":
        init_db()
    elif args.command == "create-account":
        create_account_command(args)
    elif args.command == "seed-demo":
        seed_demo(args.days, args.seed)
    elif args.command == "export-openapi":
        export_openapi()


if __name__ == "__main__":
    sys.exit(main())
