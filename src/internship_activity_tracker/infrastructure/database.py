from contextlib import contextmanager
from typing import Generator

import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# Base class for models
class Base(DeclarativeBase):
    pass


# --- Configuration ---
# Example URL structure for Neon: postgresql://user:password@host/dbname
DEFAULT_DB_URL = "sqlite:///./temp_roster.db"  # Fallback only, user wants Neon


@st.cache_resource
def get_engine():
    """
    Creates and caches the SQLAlchemy engine.
    Reads DB_URL from st.secrets.get("database", {}).get("url")
    """
    db_secrets = st.secrets.get("database", {})
    db_url = db_secrets.get("url")

    if not db_url:
        st.warning("⚠️ Database URL not found in secrets. Falling back to local SQLite for safety.")
        db_url = DEFAULT_DB_URL

    # ensure it's compatible with modern postgres drivers if needed
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    return create_engine(db_url, pool_pre_ping=True)


@st.cache_resource
def get_session_factory():
    """Creates and caches the session factory."""
    engine = get_engine()
    return sessionmaker(bind=engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager for database sessions to ensure automatic closing."""
    factory = get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """Initializes the database by creating all tables."""
    from . import models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(engine)
