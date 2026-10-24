"""
Send a simulated scenario to a RUNNING Eagle Eye backend over HTTP.

This shows the integration path an external log collector would use: it logs in, then
posts the events to POST /api/v1/activities/batch exactly like any other client.

    python -m simulator.cli --list
    python -m simulator.cli --scenario COMBINED_ANOMALY --username omar.hassan --date 2026-10-09
    (asks for the admin password; or set EAGLE_EYE_PASSWORD)

Only the Python standard library is used, so nothing extra has to be installed.
"""

import argparse
import getpass
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from simulator.catalog import Employee, find_demo_employee
from simulator.scenarios import SCENARIOS, run_scenario


def call_api(base_url: str, method: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    data = json.dumps(body, default=str).encode() if body is not None else None
    request = urllib.request.Request(base_url.rstrip("/") + path, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise SystemExit(f"API error {error.code} on {path}: {error.read().decode()}")
    except urllib.error.URLError as error:
        raise SystemExit(f"Cannot reach the API at {base_url}: {error.reason}. Is the backend running?")


def main():
    parser = argparse.ArgumentParser(description="Send a synthetic scenario to the Eagle Eye API")
    parser.add_argument("--list", action="store_true", help="list the scenarios and exit")
    parser.add_argument("--scenario", default="NORMAL_USER", choices=sorted(SCENARIOS))
    parser.add_argument("--username", help="monitored user to simulate (e.g. omar.hassan)")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today() - timedelta(days=1))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--intensity", type=int, default=1, choices=[1, 2, 3])
    parser.add_argument("--api-url", default=os.getenv("EAGLE_EYE_API_URL", "http://localhost:8000"))
    parser.add_argument("--login", default="admin", help="Eagle Eye ADMIN account")
    args = parser.parse_args()

    if args.list:
        for scenario in SCENARIOS.values():
            print(f"{scenario.id:20s} {scenario.name}")
        return
    if not args.username:
        parser.error("--username is required")

    password = os.getenv("EAGLE_EYE_PASSWORD") or getpass.getpass(f"Password for {args.login}: ")
    token = call_api(args.api_url, "POST", "/api/v1/auth/login",
                     body={"username": args.login, "password": password})["access_token"]

    query = urllib.parse.urlencode({"search": args.username, "page_size": 100})
    users = call_api(args.api_url, "GET", f"/api/v1/users?{query}", token)["items"]
    user = next((item for item in users if item["username"] == args.username), None)
    if user is None:
        raise SystemExit(f"No monitored user named {args.username}")

    employee = find_demo_employee(args.username) or Employee(user["username"], user["department"], user["job_role"])
    events = run_scenario(args.scenario, employee, args.date, seed=args.seed, intensity=args.intensity)
    batch = [{"user_id": user["id"], "source": "SIMULATOR", "is_simulated": True, **event} for event in events]
    result = call_api(args.api_url, "POST", "/api/v1/activities/batch", token, {"activities": batch})

    print(f"Sent {result['created']} simulated events for {args.username} on {args.date} ({args.scenario}).")
    for analysis in result["analyses"]:
        rules = ", ".join(rule["rule_id"] for rule in analysis["triggered_rules"]) or "none"
        print(f"  {analysis['window_date']}: risk {analysis['risk_score']} ({analysis['risk_level']}), "
              f"rules {analysis['rule_score']} [{rules}], AI {analysis['ai_score']}, alert {analysis['alert_id']}")


if __name__ == "__main__":
    main()
