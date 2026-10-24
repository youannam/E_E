"""
Database tables (SQLAlchemy ORM models).

Two kinds of people exist in the system and are stored separately on purpose:
  * Account       - people who LOG IN to Eagle Eye (administrators and security analysts).
                    Only these have password hashes.
  * MonitoredUser - the (synthetic) employees whose activity is analyzed. They never log in
                    to Eagle Eye, so no passwords are stored for them.

See docs/DATABASE_SCHEMA.md for the ER diagram.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def utc_now() -> datetime:
    # Stored without timezone info; every "created_at"-style column is UTC.
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Link table: which activities are evidence for which alert (many-to-many).
alert_activities = Table(
    "alert_activities",
    Base.metadata,
    Column("alert_id", ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True),
    Column("activity_id", ForeignKey("activities.id", ondelete="CASCADE"), primary_key=True),
)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(120), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str] = mapped_column(String(20))  # ADMIN or ANALYST: application access tier
    job_role: Mapped[str] = mapped_column(String(60), default="Security Analyst")  # business job role, separate from access tier
    permissions: Mapped[list] = mapped_column(JSON, default=list)  # Explicit per-account grants, enforced by API dependencies
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_login: Mapped[datetime | None] = mapped_column(DateTime)


class MonitoredUser(Base):
    __tablename__ = "monitored_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(60), index=True)
    job_role: Mapped[str] = mapped_column(String(60))
    job_permissions: Mapped[list] = mapped_column(JSON, default=list)  # Job-role capability profile for monitored employee
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")  # ACTIVE or INACTIVE
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_login: Mapped[datetime | None] = mapped_column(DateTime)  # latest LOGIN activity
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Highest final risk score among the user's analyzed days in the last 7 days.
    current_risk_score: Mapped[float] = mapped_column(Float, default=0)
    current_risk_level: Mapped[str] = mapped_column(String(10), default="LOW", index=True)

    activities: Mapped[list["Activity"]] = relationship(back_populates="user")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("monitored_users.id", ondelete="SET NULL"))
    device_type: Mapped[str] = mapped_column(String(30))  # WORKSTATION, USB_STORAGE, ...
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime)


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("monitored_users.id", ondelete="RESTRICT"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)  # local organization time
    event_type: Mapped[str] = mapped_column(String(30), index=True)
    resource: Mapped[str | None] = mapped_column(String(255))
    sensitivity: Mapped[str | None] = mapped_column(String(20))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    device_id: Mapped[str | None] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(20), default="API")  # API, SIMULATOR, IMPORT
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    user: Mapped[MonitoredUser] = relationship(back_populates="activities")


class BehavioralProfile(Base):
    """The latest behavioral baseline computed for a user (one row per user, updated in place)."""

    __tablename__ = "behavioral_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("monitored_users.id", ondelete="CASCADE"), unique=True)
    baseline_type: Mapped[str] = mapped_column(String(20))  # INDIVIDUAL, PEER_GROUP or DEFAULT
    window_start: Mapped[datetime | None] = mapped_column(Date)
    window_end: Mapped[datetime | None] = mapped_column(Date)
    observation_days: Mapped[int] = mapped_column(Integer, default=0)
    feature_means: Mapped[dict] = mapped_column(JSON, default=dict)
    feature_stds: Mapped[dict] = mapped_column(JSON, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class AnalysisResult(Base):
    """
    The detection result for one user on one day (the analysis window).
    Re-analysing the same day updates the same row, so there is one row per user-day.
    These rows form the user's risk history.
    """

    __tablename__ = "analysis_results"
    __table_args__ = (UniqueConstraint("user_id", "window_date", name="uq_analysis_user_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("monitored_users.id", ondelete="CASCADE"), index=True)
    window_date: Mapped[datetime] = mapped_column(Date, index=True)
    event_count: Mapped[int] = mapped_column(Integer)
    features: Mapped[dict] = mapped_column(JSON)
    baseline_type: Mapped[str] = mapped_column(String(20))
    rule_score: Mapped[float] = mapped_column(Float)
    triggered_rules: Mapped[list] = mapped_column(JSON, default=list)
    ai_status: Mapped[str] = mapped_column(String(20))  # OK or UNAVAILABLE
    ai_is_anomaly: Mapped[bool | None] = mapped_column(Boolean)
    ai_score: Mapped[float | None] = mapped_column(Float)
    ai_raw_score: Mapped[float | None] = mapped_column(Float)
    model_version: Mapped[str | None] = mapped_column(String(60))
    risk_score: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[str] = mapped_column(String(10))
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id", ondelete="SET NULL"))
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("monitored_users.id", ondelete="RESTRICT"), index=True)
    window_date: Mapped[datetime] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    risk_score: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[str] = mapped_column(String(10), index=True)
    rule_score: Mapped[float] = mapped_column(Float)
    ai_status: Mapped[str] = mapped_column(String(20))
    ai_is_anomaly: Mapped[bool | None] = mapped_column(Boolean)
    ai_score: Mapped[float | None] = mapped_column(Float)
    model_version: Mapped[str | None] = mapped_column(String(60))
    triggered_rules: Mapped[list] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)  # how many analyses were merged into it
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolution_notes: Mapped[str | None] = mapped_column(Text)

    user: Mapped[MonitoredUser] = relationship()
    assigned_to: Mapped[Account | None] = relationship()
    activities: Mapped[list[Activity]] = relationship(secondary=alert_activities, order_by=Activity.timestamp)
    history: Mapped[list["AlertHistory"]] = relationship(
        back_populates="alert", order_by="AlertHistory.created_at", cascade="all, delete-orphan"
    )


class AlertHistory(Base):
    """Every change to an alert: creation, merges, status changes and analyst notes."""

    __tablename__ = "alert_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(30))  # CREATED, UPDATED_BY_DETECTION, STATUS_CHANGED, NOTE_ADDED
    old_status: Mapped[str | None] = mapped_column(String(20))
    new_status: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    alert: Mapped[Alert] = relationship(back_populates="history")
    account: Mapped[Account | None] = relationship()


class AuditLog(Base):
    """Who did what in Eagle Eye. Never stores passwords, tokens or other secrets."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(50))  # account username, or "system"
    action: Mapped[str] = mapped_column(String(50), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(30))
    entity_id: Mapped[str | None] = mapped_column(String(50))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class RuleSetting(Base):
    """Configurable settings of one cybersecurity rule (seeded from backend/detection/rule_config.py)."""

    __tablename__ = "rule_settings"

    rule_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    weight: Mapped[float] = mapped_column(Float)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(60), unique=True)
    algorithm: Mapped[str] = mapped_column(String(120))
    training_dataset: Mapped[dict] = mapped_column(JSON, default=dict)
    trained_at: Mapped[str] = mapped_column(String(40))
    feature_schema_version: Mapped[str] = mapped_column(String(10))
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    artifact_path: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")  # ACTIVE or RETIRED
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class PasswordResetRequest(Base):
    """A user-initiated password reset request awaiting administrator review."""
    __tablename__ = "password_reset_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), index=True)
    email: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
