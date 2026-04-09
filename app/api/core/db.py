# app/api/core/db.py
"""
ChronoFlow — Database setup
SQLite for dev, Postgres for prod — swap via DATABASE_URL in .env
"""

from contextlib import contextmanager
from sqlmodel import SQLModel, Session, create_engine
from app.api.core.config import settings

# psycopg2 is the only addition for Postgres support
engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args=(
        {"check_same_thread": False}
        if settings.DATABASE_URL.startswith("sqlite")
        else {}
    ),
    pool_pre_ping=True,       # drops stale connections before using them
    pool_size=5,              # sensible default for a single-service app
    pool_recycle=300,         # recycle connections every 5 min
)


def create_tables() -> None:
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session():
    with Session(engine) as session:
        yield session