"""
API request and response models (Pydantic).

These classes ARE the API contract: FastAPI uses them to validate incoming JSON, to shape
outgoing JSON and to generate the Swagger documentation at /docs. The web dashboard
(frontend/src/api/types.ts) and the Flutter app (mobile/lib/models.dart) mirror these
field names exactly.
"""

from datetime import date, datetime, timezone
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from ai.features import RESOURCE_EVENT_TYPES

EventType = Literal["LOGIN", "LOGOUT", "FILE_ACCESS", "FILE_DOWNLOAD", "FILE_UPLOAD", "FILE_DELETE",
                    "USB_CONNECT", "USB_TRANSFER", "EMAIL_SENT", "APPLICATION_USAGE"]
Sensitivity = Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
AlertStatus = Literal["OPEN", "INVESTIGATING", "RESOLVED", "FALSE_POSITIVE"]
ActivitySource = Literal["API", "IMPORT", "SIMULATOR"]

# Some fields are called "date"; inside those classes the name `date` would refer to the
# field itself, so the type is used under this second name.
Day = date
MAX_FILE_SIZE_BYTES = 50 * 1024 ** 3  # 50 GB; anything larger is treated as invalid input
T = TypeVar("T")


def _mark_utc(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


# Two kinds of time appear in the API:
#  * Activity times (timestamp, last_activity_at, ...) are LOCAL organization time, sent without a timezone.
#  * System times (when an alert was created, when someone logged in to Eagle Eye, ...) are stored in UTC
#    and sent WITH a timezone ("...Z"), so the web and mobile apps can show them in the viewer's local time.
UtcDatetime = Annotated[datetime, AfterValidator(_mark_utc)]


class Page(BaseModel, Generic[T]):
    """Every list endpoint returns this shape."""

    items: list[T]
    total: int
    page: int
    page_size: int


# --------------------------------------------------------------------------- auth

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120, description="Username or email")
    password: str = Field(min_length=1, max_length=200)


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None
    role: Literal["ADMIN", "ANALYST"]
    job_role: str = "Security Analyst"
    permissions: list[str] = Field(default_factory=list)
    is_active: bool
    last_login: UtcDatetime | None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Seconds until the token expires")
    account: AccountOut


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9._\-]+$")
    email: str | None = Field(default=None, max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=10, max_length=200)
    role: Literal["ADMIN", "ANALYST"] = "ANALYST"
    job_role: str = Field(default="Security Analyst", min_length=2, max_length=60)
    permissions: list[str] = Field(default_factory=list)
    is_active: bool = True


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str | None = Field(default=None, min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9._\-]+$")
    email: str | None = Field(default=None, max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str | None = Field(default=None, min_length=10, max_length=200)
    role: Literal["ADMIN", "ANALYST"] | None = None
    job_role: str | None = Field(default=None, min_length=2, max_length=60)
    permissions: list[str] | None = None
    is_active: bool | None = None


# --------------------------------------------------------------------------- activities

class ActivityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int = Field(gt=0)
    timestamp: datetime = Field(description="ISO 8601. Without a timezone it is read as local organization time.")
    event_type: EventType
    resource: str | None = Field(default=None, max_length=255)
    sensitivity: Sensitivity | None = None
    file_size_bytes: int | None = Field(default=None, ge=0, le=MAX_FILE_SIZE_BYTES)
    device_id: str | None = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9._:\-]+$")
    source: ActivitySource = "API"
    is_simulated: bool = False
    details: dict = Field(default_factory=dict)

    @field_validator("details")
    @classmethod
    def limit_details_size(cls, value: dict) -> dict:
        if len(str(value)) > 2000:
            raise ValueError("details is too large (max ~2000 characters)")
        return value

    @model_validator(mode="after")
    def check_resource_fields(self):
        if self.event_type in RESOURCE_EVENT_TYPES and not self.resource:
            raise ValueError(f"resource is required for {self.event_type} events")
        if self.resource and not self.sensitivity:
            raise ValueError("sensitivity is required when a resource is given")
        return self


class ActivityBatchCreate(BaseModel):
    activities: list[ActivityCreate] = Field(min_length=1, max_length=2000)


class ActivityOut(BaseModel):
    id: int
    user_id: int
    username: str
    timestamp: datetime
    event_type: str
    resource: str | None
    sensitivity: str | None
    file_size_bytes: int | None
    device_id: str | None
    source: str
    is_simulated: bool
    details: dict


# --------------------------------------------------------------------------- analysis

class TriggeredRule(BaseModel):
    rule_id: str
    name: str
    severity: str
    contribution: float
    reason: str
    evidence: dict = Field(default_factory=dict)


class AnalysisOut(BaseModel):
    id: int
    user_id: int
    username: str
    window_date: date
    event_count: int
    features: dict[str, float]
    baseline_type: str
    rule_score: float
    triggered_rules: list[TriggeredRule]
    ai_status: Literal["OK", "UNAVAILABLE"]
    ai_is_anomaly: bool | None
    ai_score: float | None
    ai_raw_score: float | None
    model_version: str | None
    risk_score: float
    risk_level: RiskLevel
    score_breakdown: dict
    alert_id: int | None
    analyzed_at: UtcDatetime


class IngestResponse(BaseModel):
    created: int
    activity_ids: list[int]
    analyses: list[AnalysisOut]


class AnalysisRunRequest(BaseModel):
    user_id: int = Field(gt=0)
    date: Day


class ModelStatus(BaseModel):
    loaded: bool
    message: str
    version: str | None = None
    algorithm: str | None = None
    trained_at: str | None = None
    feature_schema_version: str | None = None
    feature_names: list[str] = Field(default_factory=list)
    calibration: dict = Field(default_factory=dict)
    training_dataset: dict = Field(default_factory=dict)
    metrics: dict = Field(default_factory=dict)


# --------------------------------------------------------------------------- users

class UserSummary(BaseModel):
    id: int
    username: str
    email: str | None
    department: str
    job_role: str
    job_permissions: list[str] = Field(default_factory=list)
    status: str
    is_synthetic: bool
    current_risk_score: float
    current_risk_level: RiskLevel
    alert_count: int
    open_alert_count: int
    last_activity_at: datetime | None
    last_login: datetime | None


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9._\-]+$")
    email: str | None = Field(default=None, max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    department: str = Field(min_length=2, max_length=60)
    job_role: str = Field(min_length=2, max_length=60)
    job_permissions: list[str] | None = None
    is_synthetic: bool = True


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str | None = Field(default=None, min_length=3, max_length=80, pattern=r"^[a-z0-9._\-]+$")
    email: str | None = Field(default=None, max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    department: str | None = Field(default=None, min_length=2, max_length=60)
    job_role: str | None = Field(default=None, min_length=2, max_length=60)
    job_permissions: list[str] | None = None
    status: Literal["ACTIVE", "INACTIVE"] | None = None


class BaselineOut(BaseModel):
    baseline_type: str
    observation_days: int
    window_start: date | None
    window_end: date | None
    feature_means: dict[str, float]
    feature_stds: dict[str, float]
    generated_at: UtcDatetime


class UserStatistics(BaseModel):
    period_days: int
    event_counts: dict[str, int]
    active_days: int
    average_events_per_active_day: float
    devices: list[str]


class UserDetail(UserSummary):
    profile: BaselineOut | None
    statistics: UserStatistics


class RiskHistoryPoint(BaseModel):
    window_date: date
    risk_score: float
    risk_level: RiskLevel
    rule_score: float
    ai_score: float | None
    ai_is_anomaly: bool | None
    event_count: int
    alert_id: int | None


# --------------------------------------------------------------------------- alerts

class AlertSummary(BaseModel):
    id: int
    user_id: int
    username: str
    department: str
    window_date: date
    created_at: UtcDatetime
    updated_at: UtcDatetime
    risk_score: float
    risk_level: RiskLevel
    rule_score: float
    ai_status: str
    ai_score: float | None
    ai_is_anomaly: bool | None
    model_version: str | None
    status: AlertStatus
    triggered_rule_ids: list[str]
    occurrence_count: int
    assigned_to: str | None


class AlertHistoryOut(BaseModel):
    id: int
    action: str
    old_status: str | None
    new_status: str | None
    note: str | None
    actor: str | None
    created_at: UtcDatetime


class AlertDetail(AlertSummary):
    triggered_rules: list[TriggeredRule]
    explanation: str
    resolved_at: UtcDatetime | None
    resolution_notes: str | None
    user: UserSummary
    activities: list[ActivityOut]
    history: list[AlertHistoryOut]
    analysis: AnalysisOut | None


class AlertUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AlertStatus | None = None
    note: str | None = Field(default=None, max_length=2000)
    assign_to_me: bool | None = None

    @model_validator(mode="after")
    def check_something_changes(self):
        if self.status is None and not (self.note and self.note.strip()) and self.assign_to_me is None:
            raise ValueError("Provide at least one of: status, note, assign_to_me")
        if self.status in ("RESOLVED", "FALSE_POSITIVE") and not (self.note and self.note.strip()):
            raise ValueError("A note explaining the decision is required when resolving an alert")
        return self


class AlertStatistics(BaseModel):
    total: int
    by_status: dict[str, int]
    by_level: dict[str, int]
    open_by_level: dict[str, int]


# --------------------------------------------------------------------------- dashboard

class DashboardSummary(BaseModel):
    total_users: int
    active_users: int
    active_users_definition: str
    open_alerts: int
    investigating_alerts: int
    critical_alerts: int
    high_risk_users: int
    activities_last_24h: int
    model_loaded: bool
    model_version: str | None


class RiskDistributionItem(BaseModel):
    level: RiskLevel
    count: int


class AlertsOverTimeItem(BaseModel):
    date: Day
    LOW: int
    MEDIUM: int
    HIGH: int
    CRITICAL: int
    total: int


class ActivityDistributionItem(BaseModel):
    event_type: str
    count: int


# --------------------------------------------------------------------------- simulator

class ScenarioOut(BaseModel):
    id: str
    name: str
    description: str
    expected_signals: list[str]
    suspicious: bool


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1, max_length=40)
    user_id: int = Field(gt=0)
    date: Day | None = Field(default=None, description="Day to simulate; defaults to yesterday (a complete day)")
    seed: int = Field(default=42, ge=0, le=1_000_000)
    intensity: int = Field(default=1, ge=1, le=3)


class SimulationResponse(BaseModel):
    scenario_id: str
    scenario_name: str
    date: Day
    seed: int
    intensity: int
    events_created: int
    activities: list[ActivityOut]
    analysis: AnalysisOut | None
    alert: AlertSummary | None


# --------------------------------------------------------------------------- rules

class RuleOut(BaseModel):
    rule_id: str
    name: str
    description: str
    severity: str
    required_fields: list[str]
    time_window: str
    enabled: bool
    weight: float
    parameters: dict


class RuleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    weight: float | None = Field(default=None, ge=0, le=100)
    parameters: dict | None = None


class MessageResponse(BaseModel):
    detail: str
