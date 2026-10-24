"""
Database connection.

SQLAlchemy lets us write Python classes (backend/models.py) instead of raw SQL, and the
same code works with SQLite (local demo) and PostgreSQL (by changing DATABASE_URL).
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.config import get_settings


class Base(DeclarativeBase):
    """Parent class of every table class in backend/models.py."""


def make_engine(database_url: str):
    if database_url.startswith("sqlite"):
        # FastAPI may use the connection from different threads; SQLite needs this flag for that.
        engine = create_engine(database_url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection, connection_record):
            # SQLite ignores foreign keys unless this is switched on for every connection.
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    return create_engine(database_url, pool_pre_ping=True)


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI dependency: one database session per request, always closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
