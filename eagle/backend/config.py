"""
Application settings, read from environment variables (and a local .env file).

All secrets come from the environment. Nothing secret is written in the source code.
"""

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

MIN_SECRET_LENGTH = 32


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


@dataclass
class Settings:
    environment: str = "development"
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    database_url: str = "sqlite:///./eagle_eye.db"
    cors_origins: list[str] = field(default_factory=list)
    org_timezone: str = "Africa/Cairo"
    model_dir: str = "ai/models"
    risk_rule_weight: float = 0.4
    risk_ai_weight: float = 0.6
    risk_medium_min: float = 25
    risk_high_min: float = 50
    risk_critical_min: float = 75
    alert_threshold: float = 50
    admin_email: str = ""
    analyst_email: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True
    smtp_analyst_username: str = ""
    smtp_analyst_password: str = ""
    smtp_analyst_from_email: str = ""

    def validate(self) -> None:
        """Stop the application early with a clear message instead of running insecurely."""
        if len(self.jwt_secret_key) < MIN_SECRET_LENGTH:
            raise RuntimeError(
                "JWT_SECRET_KEY is missing or shorter than 32 characters. Create a .env file "
                "(copy .env.example) and set it, e.g. with: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        if abs(self.risk_rule_weight + self.risk_ai_weight - 1.0) > 1e-6:
            raise RuntimeError("RISK_RULE_WEIGHT + RISK_AI_WEIGHT must equal 1.0")
        if not (0 < self.risk_medium_min < self.risk_high_min < self.risk_critical_min <= 100):
            raise RuntimeError("Risk level boundaries must satisfy 0 < MEDIUM < HIGH < CRITICAL <= 100")

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


def load_settings() -> Settings:
    load_dotenv()
    origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return Settings(
        environment=os.getenv("ENVIRONMENT", "development"),
        jwt_secret_key=os.getenv("JWT_SECRET_KEY", ""),
        access_token_expire_minutes=_int("ACCESS_TOKEN_EXPIRE_MINUTES", 60),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./eagle_eye.db"),
        cors_origins=[origin.strip() for origin in origins.split(",") if origin.strip()],
        org_timezone=os.getenv("ORG_TIMEZONE", "Africa/Cairo"),
        model_dir=os.getenv("MODEL_DIR", "ai/models"),
        risk_rule_weight=_float("RISK_RULE_WEIGHT", 0.4),
        risk_ai_weight=_float("RISK_AI_WEIGHT", 0.6),
        risk_medium_min=_float("RISK_MEDIUM_MIN", 25),
        risk_high_min=_float("RISK_HIGH_MIN", 50),
        risk_critical_min=_float("RISK_CRITICAL_MIN", 75),
        alert_threshold=_float("ALERT_THRESHOLD", 50),
        admin_email=os.getenv("ADMIN_EMAIL", "").strip(),
        analyst_email=os.getenv("ANALYST_EMAIL", "").strip(),
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com").strip(),
        smtp_port=_int("SMTP_PORT", 587),
        smtp_username=os.getenv("SMTP_USERNAME", "").strip(),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_from_email=os.getenv("SMTP_FROM_EMAIL", "").strip(),
        smtp_use_tls=os.getenv("SMTP_USE_TLS", "true").strip().lower() in ("1", "true", "yes"),
        smtp_analyst_username=os.getenv("SMTP_ANALYST_USERNAME", "").strip(),
        smtp_analyst_password=os.getenv("SMTP_ANALYST_PASSWORD", ""),
        smtp_analyst_from_email=os.getenv("SMTP_ANALYST_FROM_EMAIL", os.getenv("ANALYST_EMAIL", "")).strip(),
    )


@lru_cache
def get_settings() -> Settings:
    """Settings are read once and reused (tests can call get_settings.cache_clear())."""
    return load_settings()
