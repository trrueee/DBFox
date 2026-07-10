"""Shared pytest fixtures for DBFox engine tests.

Fixture lifecycle (fastest → slowest, ordered by scope):

* ``db_session``          function  in-memory SQLite :memory: + StaticPool   ~0.01 s
* ``test_datasource``     function  copy-on-write from session-shared file   ~0.05 s
* ``_shared_test_db_file`` session  one-time tables + seed data (~20 tables) ~0.15 s

The session-shared ``_shared_test_db_file`` eliminates ~3 s of repeated
``_init_test_db()`` work for every ``test_datasource`` consumer.
"""
import os
os.environ["DBFOX_BYPASS_CONFIRMATION"] = "1"
os.environ["DBFOX_TESTING"] = "1"
os.environ["DBFOX_ALLOW_GUARDRAIL_BYPASS"] = "1"

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


def _ensure_test_fts5(engine) -> None:
    """Create FTS5 virtual table in test database if it doesn't exist."""
    from sqlalchemy import text as sa_text
    from engine.models import FTS5_DDL
    try:
        with engine.connect() as conn:
            conn.execute(sa_text("SELECT 1 FROM schema_search_fts LIMIT 0"))
    except Exception:
        with engine.connect() as conn:
            conn.execute(sa_text(FTS5_DDL))
            conn.commit()


def _make_db_session():
    """Create an isolated in-memory SQLite session.

    StaticPool ensures a single connection is reused so that tables created
    via Base.metadata.create_all are visible to the yielded session.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    _ensure_test_fts5(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    return session, engine


@pytest.fixture
def db_session():
    """Function-scoped in-memory SQLite session (default — full isolation)."""
    session, _engine = _make_db_session()
    yield session
    session.close()


@pytest.fixture(scope="module")
def db_session_module():
    """Module-scoped in-memory SQLite session.

    Use in test classes that only perform read-only catalog operations
    and do not modify tables within the same module.
    """
    session, _engine = _make_db_session()
    yield session
    session.close()


def _make_spider_ds(db_session, db_key: str):
    """Create a DataSource row pointing at a Spider SQLite database."""
    if db_key not in SPIDER_SQLITE_DBS:
        raise KeyError(f"Invalid Spider DB key '{db_key}'. Available keys: {list(SPIDER_SQLITE_DBS.keys())}")
    sqlite_path = SPIDER_SQLITE_DBS[db_key]
    if not Path(sqlite_path).exists():
        import pytest
        pytest.skip(f"Spider SQLite DB file not found: {sqlite_path}")

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


def _init_test_db(db_path: str) -> str:
    """Create a test SQLite database with sample tables."""
    import sqlite3
    from pathlib import Path

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (parent_id) REFERENCES categories (id)
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sku TEXT NOT NULL UNIQUE,
            category_id INTEGER NOT NULL,
            price REAL NOT NULL,
            stock INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            FOREIGN KEY (category_id) REFERENCES categories (id)
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            total_amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            payment_method TEXT,
            shipping_address TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products (id)
        );
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            transaction_id TEXT,
            payment_method TEXT NOT NULL DEFAULT 'alipay',
            created_at TEXT NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS shipping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            tracking_number TEXT,
            carrier TEXT,
            status TEXT NOT NULL DEFAULT 'packing',
            shipped_at TEXT,
            delivered_at TEXT,
            FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS inventory_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            change_amount INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS coupons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            discount_type TEXT NOT NULL,
            value REAL NOT NULL,
            min_spend REAL NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS coupon_usages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coupon_id INTEGER NOT NULL,
            order_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (coupon_id) REFERENCES coupons (id) ON DELETE CASCADE,
            FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        CREATE TABLE IF NOT EXISTS user_addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            consignee TEXT NOT NULL,
            phone TEXT NOT NULL,
            province TEXT NOT NULL,
            city TEXT NOT NULL,
            district TEXT,
            address TEXT NOT NULL,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact TEXT NOT NULL,
            phone TEXT NOT NULL,
            address TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            total_cost REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (supplier_id) REFERENCES suppliers (id)
        );
        CREATE TABLE IF NOT EXISTS purchase_order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            cost REAL NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY (purchase_order_id) REFERENCES purchase_orders (id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products (id)
        );
        CREATE TABLE IF NOT EXISTS analytics_clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            ip TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            description TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            ip TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (admin_id) REFERENCES users (id)
        );
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            score REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
        );
    """)
    conn.commit()
    # Seed minimal data for tests
    now = "2025-01-15T12:00:00"
    conn.execute("INSERT OR IGNORE INTO users (id, username, email, role, created_at) VALUES (1, 'admin', 'admin@test.local', 'admin', ?)", (now,))
    conn.execute("INSERT OR IGNORE INTO users (id, username, email, role, created_at) VALUES (2, 'testuser', 'test@test.local', 'user', ?)", (now,))
    conn.execute("INSERT OR IGNORE INTO categories (id, name, created_at) VALUES (1, 'Test Category', ?)", (now,))
    conn.execute("INSERT OR IGNORE INTO products (id, name, sku, category_id, price, stock, status, created_at) VALUES (1, 'Test Product', 'SKU001', 1, 99.99, 50, 'active', ?)", (now,))
    conn.execute("INSERT OR IGNORE INTO orders (id, user_id, total_amount, status, shipping_address, created_at, updated_at) VALUES (1, 1, 199.99, 'completed', '123 Test St', ?, ?)", (now, now))
    conn.execute("INSERT OR IGNORE INTO order_items (id, order_id, product_id, price, quantity, created_at) VALUES (1, 1, 1, 99.99, 2, ?)", (now,))
    conn.execute("INSERT OR IGNORE INTO payments (id, order_id, amount, status, payment_method, created_at) VALUES (1, 1, 199.99, 'success', 'alipay', ?)", (now,))
    conn.execute("INSERT OR IGNORE INTO shipping (id, order_id, tracking_number, carrier, status, shipped_at, delivered_at) VALUES (1, 1, 'TRACK001', 'sf', 'delivered', ?, ?)", (now, now))
    conn.execute("INSERT OR IGNORE INTO reviews (id, product_id, user_id, rating, comment, created_at) VALUES (1, 1, 1, 5, 'Great!', ?)", (now,))
    conn.commit()
    conn.close()
    return db_path


def _make_datasource(db_session, db_dir: Path, ds_id: str | None = None) -> DataSource:
    """Create a SQLite DataSource row pointing at a test database."""
    db_file = db_dir / "test_engine.db"
    db_path = _init_test_db(str(db_file))

    ds = DataSource(
        id=ds_id or str(uuid.uuid4()),
        name="test_sqlite",
        host="localhost",
        port=0,
        database_name=db_path,
        username="test",
        db_type="sqlite",
        status="active",
    )
    db_session.add(ds)
    db_session.commit()
    return ds


@pytest.fixture
def test_datasource(db_session, tmp_path):
    """Function-scoped SQLite datasource — full per-test isolation (default)."""
    return _make_datasource(db_session, tmp_path)


@pytest.fixture(scope="module")
def test_datasource_module(db_session_module, tmp_path_factory):
    """Module-scoped SQLite datasource.

    Use in test classes that treat the test database as read-only or
    whose modifications don't conflict within the same module.
    Saves ~0.5 s of DB-init overhead per additional test.
    """
    db_dir = tmp_path_factory.mktemp("ds_module")
    return _make_datasource(db_session_module, db_dir, ds_id="ds-test-module")


@pytest.fixture(autouse=True)
def reset_checkpointer():
    """Reset the global _SHARED_MEMORY_SAVER before and after every test."""
    from engine.agent_core import checkpointer
    checkpointer._SHARED_MEMORY_SAVER = None
    yield
    checkpointer._SHARED_MEMORY_SAVER = None


@pytest.fixture(autouse=True)
def mock_openai_client(monkeypatch):
    import engine.llm.factory
    orig_create = engine.llm.factory.create_openai_client

    def fake_create(*args, **kwargs):
        if not kwargs.get("api_key"):
            kwargs["api_key"] = "mock-key-for-testing"
        return orig_create(*args, **kwargs)

    monkeypatch.setattr(engine.llm.factory, "create_openai_client", fake_create)


@pytest.fixture(autouse=True)
def mock_agent_progress_judge(monkeypatch, request):
    """Progress Judge requires LLM credentials; without real keys use the
    module's rule-based fallback (mirrors the legacy routing logic)."""
    if request.node.get_closest_marker("real_llm") is not None:
        return

    from engine.agent.nodes import progress_node

    def fake_judge_progress(state, config):
        escalate_result = progress_node._check_escalate(state)
        if escalate_result:
            return escalate_result
        return progress_node._rule_fallback(state)

    monkeypatch.setattr(progress_node, "judge_progress", fake_judge_progress)



