"""Database engine, session factory and the declarative base shared by all modules.

Each module defines its own tables in `_internal/models.py` on this `Base`. A table may
reference a table of a lower module by a string foreign key (`ForeignKey("users.id")`);
references to higher modules are plain ID columns (see docs/schema.md).
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

# Stable constraint names, so migrations can drop them by name.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def database_url(url: str | None = None) -> URL:
    """Parse a database URL and force the psycopg 3 driver."""
    parsed = make_url(url if url is not None else get_settings().database_url)
    return parsed.set(drivername="postgresql+psycopg")


@lru_cache
def get_engine() -> Engine:
    return create_engine(database_url(), pool_pre_ping=True)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a session that is closed after the request."""
    with _session_factory()() as session:
        yield session
