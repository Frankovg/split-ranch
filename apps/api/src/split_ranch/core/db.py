"""Database engine and session factory (SQLAlchemy 2.0, psycopg 3, sync)."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from split_ranch.core.settings import Settings, sqlalchemy_url


def create_db_engine(settings: Settings) -> Engine:
    return create_engine(
        sqlalchemy_url(settings.database_url),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        # Supabase transaction pooler does not keep session state: no prepared statements.
        connect_args={"prepare_threshold": None},
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=True)


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one session per request.

    Use cases commit explicitly; anything left uncommitted is rolled back here.
    """
    factory: sessionmaker[Session] = request.app.state.session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()
