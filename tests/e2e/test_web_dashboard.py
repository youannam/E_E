"""
Browser end-to-end test of the web dashboard against the REAL running backend.

Requirements:
  * backend running (uvicorn backend.main:app) with the demo data (python -m backend.cli seed-demo)
  * web dashboard running (cd frontend && npm run dev)
  * pip install -r requirements-dev.txt && python -m playwright install chromium

Run:  RUN_E2E=1 pytest tests/e2e -v        (Windows PowerShell: $env:RUN_E2E=1; pytest tests/e2e -v)

Settings (environment variables): EAGLE_EYE_WEB_URL (default http://localhost:5173),
EAGLE_EYE_API_URL (default http://localhost:8000), EAGLE_EYE_ADMIN_PASSWORD and
EAGLE_EYE_ANALYST_PASSWORD (default: read from demo_credentials.txt).
Note: this test adds a simulated day and changes an alert in the demo database.
"""

import json
import os
import re
import urllib.request
from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")

WEB_URL = os.getenv("EAGLE_EYE_WEB_URL", "http://localhost:5173")
API_URL = os.getenv("EAGLE_EYE_API_URL", "http://localhost:8000")
CREDENTIALS = Path(__file__).resolve().parents[2] / "demo_credentials.txt"
pytestmark = pytest.mark.e2e


def demo_password(role: str) -> str:
    from_env = os.getenv(f"EAGLE_EYE_{role}_PASSWORD")
    if from_env:
        return from_env
    match = re.search(rf"{role}\s+username: \S+\s+password: (\S+)", CREDENTIALS.read_text())
    return match.group(1)


def api(method: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    request = urllib.request.Request(f"{API_URL}/api/v1{path}", method=method,
                                     data=json.dumps(body).encode() if body else None,
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


@pytest.fixture(scope="module")
def admin_token():
    return api("POST", "/auth/login", body={"username": "admin", "password": demo_password("ADMIN")})["access_token"]


@pytest.fixture
def page():
    with playwright_api.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.console_errors = []
        page.on("pageerror", lambda error: page.console_errors.append(str(error)))
        yield page
        browser.close()


def log_in(page, username: str, password: str):
    page.goto(WEB_URL)
    page.fill("#username", username)
    page.fill("#password", password)
    page.click("button[type=submit]")


def test_wrong_password_shows_error(page):
    log_in(page, "admin", "definitely-wrong-password")
    page.wait_for_selector(".form-error")
    assert "Invalid username or password" in page.inner_text(".form-error")


def test_dashboard_shows_backend_numbers(page, admin_token):
    summary = api("GET", "/dashboard/summary", admin_token)
    log_in(page, "admin", demo_password("ADMIN"))
    page.wait_for_selector(".stat-strip")
    strip = page.inner_text(".stat-strip")
    assert str(summary["total_users"]) in strip
    assert "Alerts per day" in page.content()
    assert page.console_errors == []


def test_simulation_alert_investigation_flow(page, admin_token):
    log_in(page, "admin", demo_password("ADMIN"))
    page.wait_for_selector(".stat-strip")

    # Run the combined scenario from the Simulation center (real pipeline).
    page.goto(f"{WEB_URL}/#/simulation")
    page.wait_for_selector(".scenario")
    page.check("input[value=COMBINED_ANOMALY]")
    page.select_option(".sim-params select >> nth=0", label="nour.samir (Software Engineer)")
    page.fill(".sim-params input[type=number]", "777")
    page.click("text=Run simulation")
    page.wait_for_selector(".result .breakdown", timeout=60_000)
    assert page.locator(".simulated-tag").count() > 10
    alert_link = page.locator(".result a[href^='#/alerts/']").first
    alert_id = int(alert_link.get_attribute("href").rsplit("/", 1)[1])

    # The same alert exists in the API with the same score shown in the page.
    alert = api("GET", f"/alerts/{alert_id}", admin_token)
    assert alert["ai_status"] == "OK" and alert["triggered_rule_ids"]

    # Investigate: open the alert, start investigating (with confirmation), then check persistence.
    alert_link.click()
    page.wait_for_selector(".breakdown")
    assert alert["username"] in page.inner_text("h1")
    if alert["status"] == "OPEN":
        page.click("text=Start investigating")
        page.click(".dialog button:has-text('Start investigating')")
        page.wait_for_selector(".form-success")
        assert api("GET", f"/alerts/{alert_id}", admin_token)["status"] == "INVESTIGATING"

    page.fill("#note", "E2E test note: checked with the line manager.")
    page.click("text=Add note")
    page.wait_for_selector("text=E2E test note")

    # Filtering the alert list by status finds it.
    page.goto(f"{WEB_URL}/#/alerts")
    page.select_option("select >> nth=0", "INVESTIGATING")
    page.wait_for_selector(f"a[href='#/alerts/{alert_id}']")
    assert page.console_errors == []


def test_analyst_cannot_run_simulations(page):
    log_in(page, "analyst", demo_password("ANALYST"))
    page.wait_for_selector(".stat-strip")
    page.goto(f"{WEB_URL}/#/simulation")
    page.wait_for_selector(".scenario")
    assert page.is_disabled("text=Run simulation")
