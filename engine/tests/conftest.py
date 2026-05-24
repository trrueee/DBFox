"""Shared pytest fixtures for DataBox engine tests."""
import os
os.environ["DATABOX_BYPASS_CONFIRMATION"] = "1"
os.environ["DATABOX_TESTING"] = "1"

import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from engine.db import Base
from engine import models  # ensure all models are registered with Base
from engine.models import DataSource


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


@pytest.fixture
def demo_datasource(db_session):
    """Create a demo datasource row for testing."""
    ds = DataSource(
        id=str(uuid.uuid4()),
        name="test_demo",
        host="demo",
        port=3306,
        database_name="demo_shop",
        username="demo",
        password_ciphertext="test",
        password_nonce="test",
        status="active",
    )
    db_session.add(ds)
    db_session.commit()
    return ds
