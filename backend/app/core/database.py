"""Engine, ORM base and the per-request session."""

from typing import TYPE_CHECKING

from fastapi import Request  # noqa: TC002  FastAPI reads this annotation at runtime to inject the request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

if TYPE_CHECKING:
    from collections.abc import Iterator


class Base(DeclarativeBase):
    """Base class of every ORM table."""


def create_db_engine(url: str) -> Engine:
    """Connect to the database and create any missing tables."""
    # SQLite connections are used across FastAPI's threadpool and event loop.
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)
    Base.metadata.create_all(engine)  # shortcut: no migrations; add Alembic before the schema changes
    return engine


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one session per request, closed when the request ends."""
    with Session(request.app.state.engine, expire_on_commit=False) as session:
        yield session
