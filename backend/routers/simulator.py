"""
Simulation Center endpoints.

The simulator only GENERATES events. They are then ingested through exactly the same
code path as real events (backend/ingestion.py), so the rules, the AI model and the
alert logic all run for real. No alert is ever written directly by the simulator.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.audit import record_audit
from backend.database import get_db
from backend.detection.alerts import find_alert_for_day
from backend.ingestion import IngestionError, ingest_activities
from backend.models import Account, Activity, AnalysisResult, MonitoredUser
from backend.routers.common import get_or_404
from backend.schemas import ActivityCreate, ScenarioOut, SimulationRequest, SimulationResponse
from backend.security import require_analyst_or_admin
from backend.serializers import activity_out, alert_summary, analysis_out
from backend.timeutils import org_now, org_today
from simulator.catalog import Employee, find_demo_employee
from simulator.scenarios import SCENARIOS, run_scenario

router = APIRouter(prefix="/simulator", tags=["Simulator"])
MAX_RETURNED_ACTIVITIES = 300


def employee_profile(user: MonitoredUser) -> Employee:
    """Use the demo employee's habits if known, otherwise sensible defaults for the user's role."""
    known = find_demo_employee(user.username)
    if known:
        return known
    night_shift = user.job_role == "Night Operations Technician"
    return Employee(user.username, user.department, user.job_role, 1.0, 0 if night_shift else 9, night_shift)


@router.get("/scenarios", response_model=list[ScenarioOut], summary="Available simulation scenarios")
def list_scenarios(_: Account = Depends(require_analyst_or_admin)):
    return [ScenarioOut(id=s.id, name=s.name, description=s.description, expected_signals=s.expected_signals,
                        suspicious=s.suspicious) for s in SCENARIOS.values()]




@router.get("/targets", summary="Minimal monitored-user list for authorized detection runs")
def list_simulation_targets(db: Session = Depends(get_db), _: Account = Depends(require_analyst_or_admin)):
    return [
        {"id": user.id, "username": user.username, "job_role": user.job_role, "department": user.department}
        for user in db.scalars(select(MonitoredUser).where(MonitoredUser.status == "ACTIVE").order_by(MonitoredUser.username))
    ]


@router.post("/run", response_model=SimulationResponse, status_code=201,
             summary="Generate a synthetic scenario and process it through the real pipeline (analyst or admin)")
def run_simulation(body: SimulationRequest, db: Session = Depends(get_db), admin: Account = Depends(require_analyst_or_admin)):
    if body.scenario_id not in SCENARIOS:
        raise HTTPException(status_code=422, detail=f"Unknown scenario '{body.scenario_id}'")
    user = get_or_404(db, MonitoredUser, body.user_id, "User")
    day = body.date or (org_today() - timedelta(days=1))  # yesterday: a complete day, no future timestamps
    if day > org_today():
        raise HTTPException(status_code=422, detail="Cannot simulate a future day")

    events = run_scenario(body.scenario_id, employee_profile(user), day, seed=body.seed, intensity=body.intensity)
    now = org_now()
    events = [event for event in events if event["timestamp"] <= now]  # when simulating today, skip future events
    if not events:
        raise HTTPException(status_code=422, detail="No events before the current time. Choose an earlier date.")

    items = [ActivityCreate(user_id=user.id, source="SIMULATOR", is_simulated=True, **event) for event in events]
    try:
        activities, _ = ingest_activities(db, items)
    except IngestionError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message)

    analysis = db.scalar(select(AnalysisResult).where(AnalysisResult.user_id == user.id,
                                                      AnalysisResult.window_date == day))
    alert = find_alert_for_day(db, user.id, day)
    record_audit(db, admin.username, "SIMULATION_RUN", "monitored_user", user.id,
                 {"scenario": body.scenario_id, "date": day.isoformat(), "seed": body.seed,
                  "intensity": body.intensity, "events": len(activities)})
    db.commit()

    ids = [activity.id for activity in activities[:MAX_RETURNED_ACTIVITIES]]
    saved = list(db.scalars(select(Activity).where(Activity.id.in_(ids)).order_by(Activity.timestamp)))
    return SimulationResponse(
        scenario_id=body.scenario_id, scenario_name=SCENARIOS[body.scenario_id].name, date=day, seed=body.seed,
        intensity=body.intensity, events_created=len(activities), activities=[activity_out(a) for a in saved],
        analysis=analysis_out(db, analysis) if analysis else None,
        alert=alert_summary(alert) if alert else None,
    )
