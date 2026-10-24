"""Activity ingestion and the activity log."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.audit import record_audit
from backend.database import get_db
from backend.ingestion import IngestionError, ingest_activities
from backend.models import Account, Activity, MonitoredUser
from backend.routers.common import Pagination, paginate
from backend.schemas import ActivityBatchCreate, ActivityCreate, ActivityOut, ActivitySource, EventType, IngestResponse, Page, Sensitivity
from backend.security import require_admin
from backend.serializers import activity_out, analysis_out

router = APIRouter(prefix="/activities", tags=["Activities"])


def run_ingestion(db: Session, items: list[ActivityCreate], admin: Account) -> IngestResponse:
    try:
        activities, analyses = ingest_activities(db, items)
    except IngestionError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message)
    record_audit(db, admin.username, "ACTIVITIES_INGESTED", "activity", None,
                 {"count": len(activities), "analyzed_days": len(analyses)})
    db.commit()
    return IngestResponse(created=len(activities), activity_ids=[activity.id for activity in activities],
                          analyses=[analysis_out(db, analysis) for analysis in analyses])


@router.post("", response_model=IngestResponse, status_code=201,
             summary="Ingest one activity and analyze its day (admin)")
def create_activity(body: ActivityCreate, db: Session = Depends(get_db), admin: Account = Depends(require_admin)):
    return run_ingestion(db, [body], admin)


@router.post("/batch", response_model=IngestResponse, status_code=201,
             summary="Ingest up to 2000 activities and analyze the affected days (admin)")
def create_activities_batch(body: ActivityBatchCreate, db: Session = Depends(get_db),
                            admin: Account = Depends(require_admin)):
    return run_ingestion(db, body.activities, admin)


@router.get("", response_model=Page[ActivityOut], summary="Activity log with filters, newest first")
def list_activities(
    user_id: int | None = Query(None, gt=0),
    event_type: EventType | None = None,
    sensitivity: Sensitivity | None = None,
    source: ActivitySource | None = None,
    start: datetime | None = Query(None, description="From this local time (inclusive)"),
    end: datetime | None = Query(None, description="Until this local time (exclusive)"),
    search: str | None = Query(None, max_length=120, description="Part of the resource path or username"),
    pagination: Pagination = Depends(),
    db: Session = Depends(get_db),
    _: Account = Depends(require_admin),
):
    query = select(Activity).join(MonitoredUser)
    if user_id:
        query = query.where(Activity.user_id == user_id)
    if event_type:
        query = query.where(Activity.event_type == event_type)
    if sensitivity:
        query = query.where(Activity.sensitivity == sensitivity)
    if source:
        query = query.where(Activity.source == source)
    if start:
        query = query.where(Activity.timestamp >= start.replace(tzinfo=None))
    if end:
        query = query.where(Activity.timestamp < end.replace(tzinfo=None))
    if search:
        query = query.where(or_(Activity.resource.ilike(f"%{search}%"), MonitoredUser.username.ilike(f"%{search}%")))
    rows, total = paginate(db, query.order_by(Activity.timestamp.desc(), Activity.id.desc()), pagination)
    return Page(items=[activity_out(row) for row in rows], total=total,
                page=pagination.page, page_size=pagination.page_size)
