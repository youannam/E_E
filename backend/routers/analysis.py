"""Manual analysis and AI model status."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.audit import record_audit
from backend.database import get_db
from backend.detection import anomaly_service
from backend.detection.pipeline import analyze_user_day
from backend.models import Account, MonitoredUser
from backend.routers.common import get_or_404
from backend.schemas import AnalysisOut, AnalysisRunRequest, ModelStatus
from backend.security import require_admin, require_analyst_or_admin
from backend.serializers import analysis_out

router = APIRouter(tags=["Detection"])


@router.post("/analysis/run", response_model=AnalysisOut, summary="Re-run detection for one user-day (analyst or admin)")
def run_analysis(body: AnalysisRunRequest, db: Session = Depends(get_db), admin: Account = Depends(require_analyst_or_admin)):
    user = get_or_404(db, MonitoredUser, body.user_id, "User")
    analysis = analyze_user_day(db, user, body.date)
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"No activity for user {user.id} on {body.date}")
    record_audit(db, admin.username, "ANALYSIS_RUN", "analysis", analysis.id,
                 {"user_id": user.id, "date": body.date.isoformat()})
    db.commit()
    return analysis_out(db, analysis)


def model_status() -> ModelStatus:
    detector = anomaly_service.get_detector()
    if detector is None:
        return ModelStatus(loaded=False, message="No trained model loaded. Detection uses rules only. "
                                                 "Train one with: python -m ai.train")
    meta = detector.metadata
    return ModelStatus(
        loaded=True, message="Model loaded", version=detector.version, algorithm=meta.get("algorithm"),
        trained_at=meta.get("trained_at"), feature_schema_version=meta.get("feature_schema_version"),
        feature_names=meta.get("feature_names", []), calibration=meta.get("calibration", {}),
        training_dataset=meta.get("training_dataset", {}), metrics=meta.get("metrics", {}),
    )


@router.get("/models/status", response_model=ModelStatus, summary="Which AI model is loaded and how it was evaluated")
def get_model_status(_: Account = Depends(require_analyst_or_admin)):
    return model_status()


@router.post("/models/reload", response_model=ModelStatus, summary="Load the newest trained model from disk (admin)")
def reload_model(db: Session = Depends(get_db), admin: Account = Depends(require_admin)):
    anomaly_service.load_detector()
    anomaly_service.register_model_version(db)
    status = model_status()
    record_audit(db, admin.username, "MODEL_RELOADED", "model", status.version)
    db.commit()
    return status
