"""Shared pytest fixtures for DataBox engine tests."""
import os
os.environ["DATABOX_BYPASS_CONFIRMATION"] = "1"
os.environ["DATABOX_TESTING"] = "1"

import uuid
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from engine.db import Base
from engine import models  # ensure all models are registered with Base
from engine.models import DataSource

# ---------------------------------------------------------------------------
# Spider SQLite database paths (from .agent_eval/spider/database/)
# ---------------------------------------------------------------------------

_SPIDER_DIR = Path(__file__).resolve().parent.parent.parent / ".agent_eval" / "spider" / "database"

SPIDER_SQLITE_DBS = {
    "concert_singer": str(_SPIDER_DIR / "concert_singer" / "concert_singer.sqlite"),
    "pets_1": str(_SPIDER_DIR / "pets_1" / "pets_1.sqlite"),
    "singer": str(_SPIDER_DIR / "singer" / "singer.sqlite"),
}


@pytest.fixture
def db_session():
    """In-memory SQLite session — isolated from production databox_local.db.

    StaticPool ensures a single connection is reused so that tables created
    via Base.metadata.create_all are visible to the yielded session.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def _make_spider_ds(db_session, db_key: str):
    """Create a DataSource row pointing at a Spider SQLite database."""
    sqlite_path = SPIDER_SQLITE_DBS.get(db_key)
    if not sqlite_path or not Path(sqlite_path).exists():
        raise FileNotFoundError(f"Spider SQLite DB not found: {sqlite_path}")

    ds_id = f"ds-spider-{db_key.replace('_', '-')}"
    from engine.models import DataSource
    existing = db_session.query(DataSource).filter(DataSource.id == ds_id).first()
    if existing:
        return existing
    ds = DataSource(
        id=ds_id,
        name=f"Spider {db_key}",
        host="localhost",
        port=0,
        database_name=sqlite_path,
        username="",
        password_ciphertext="",
        password_nonce="",
        password_key_version="v1",
        db_type="sqlite",
        status="active",
    )
    db_session.add(ds)
    db_session.commit()
    return ds


@pytest.fixture
def spider_concert_singer(db_session):
    """Spider concert_singer: singer(8 rows), concert(9 rows), singer_in_concert."""
    return _make_spider_ds(db_session, "concert_singer")


@pytest.fixture
def spider_pets_1(db_session):
    """Spider pets_1: Students, Pets, Has_Pet."""
    return _make_spider_ds(db_session, "pets_1")


@pytest.fixture
def spider_singer(db_session):
    """Spider singer: singer(8), song(8)."""
    return _make_spider_ds(db_session, "singer")


@pytest.fixture
def spider_datasource(db_session):
    """Default Spider datasource (concert_singer)."""
    return _make_spider_ds(db_session, "concert_singer")


@pytest.fixture
def demo_datasource(db_session):
    """Backward-compat: Spider concert_singer as default test datasource."""
    return _make_spider_ds(db_session, "concert_singer")
