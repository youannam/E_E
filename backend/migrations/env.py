"""
Alembic migration environment.

Migrations are versioned scripts that create or change database tables, so every team
member (and a future PostgreSQL server) ends up with exactly the same schema.
Create a new migration after changing backend/models.py with:
    alembic revision --autogenerate -m "describe the change"
"""

from alembic import context

from backend import models  # noqa: F401  (importing registers every table on Base.metadata)
from backend.database import Base, engine

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=str(engine.url), target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        # render_as_batch lets Alembic alter tables on SQLite, which has limited ALTER TABLE support.
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
