"""Shared pytest fixtures for DBFox engine tests.

Fixture lifecycle (fastest → slowest, ordered by scope):

* ``db_session``          function  isolated copy of one migrated template
* ``test_datasource``     function  isolated copy of one seeded template
* template databases      session   built once, then copied per consumer

Templates are copied only after their creating connection is closed.  Tests
keep file-level isolation without repeating migrations or the large seed SQL.
"""
from pathlib import Path
from shutil import copy2

import uuid
import pytest
from sqlalchemy.orm import sessionmaker
from engine.models import DataSource
from engine.db import build_metadata_engine
from engine.tests.support.metadata import (
    create_migrated_metadata_engine,
    sqlite_metadata_url,
)

def _open_db_session(database_path: Path):
    """Open one isolated copy of the migrated metadata template."""
    engine = build_metadata_engine(sqlite_metadata_url(database_path))
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    return session, engine


@pytest.fixture(scope="session")
def metadata_template_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    template = tmp_path_factory.mktemp("metadata_template") / "metadata.db"
    engine = create_migrated_metadata_engine(template)
    engine.dispose()
    return template


@pytest.fixture
def db_session(tmp_path: Path, metadata_template_file: Path):
    """Function-scoped metadata session backed by an isolated template copy."""
    database_path = tmp_path / "metadata.db"
    copy2(metadata_template_file, database_path)
    session, engine = _open_db_session(database_path)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(name="client")
def api_client_fixture(db_session):
    """Authenticated FastAPI client with dependency overrides restored exactly."""
    from fastapi.testclient import TestClient

    from engine.db import get_db
    from engine.main import LOCAL_SECURE_TOKEN, app

    previous_overrides = dict(app.dependency_overrides)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(
            app,
            headers={"X-Local-Token": LOCAL_SECURE_TOKEN},
        ) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


@pytest.fixture(scope="module")
def db_session_module(
    tmp_path_factory: pytest.TempPathFactory,
    metadata_template_file: Path,
):
    """Module-scoped file-backed Alembic-upgraded SQLite session.

    Use in test classes that only perform read-only catalog operations
    and do not modify tables within the same module.
    """
    database_path = tmp_path_factory.mktemp("metadata_module") / "metadata.db"
    copy2(metadata_template_file, database_path)
    session, engine = _open_db_session(database_path)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


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


def _make_datasource(
    db_session,
    db_dir: Path,
    template: Path,
    ds_id: str | None = None,
) -> DataSource:
    """Create a DataSource row pointing at an isolated seeded database copy."""
    db_file = db_dir / "test_engine.db"
    copy2(template, db_file)

    ds = DataSource(
        id=ds_id or str(uuid.uuid4()),
        name="test_sqlite",
        host="localhost",
        port=0,
        database_name=str(db_file),
        username="test",
        db_type="sqlite",
        status="active",
    )
    return ds


@pytest.fixture(scope="session")
def datasource_template_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    template = tmp_path_factory.mktemp("datasource_template") / "seeded.db"
    _init_test_db(str(template))
    return template


@pytest.fixture
def test_datasource(db_session, tmp_path, datasource_template_file: Path):
    """Function-scoped SQLite datasource — full per-test isolation (default)."""
    return _make_datasource(db_session, tmp_path, datasource_template_file)


@pytest.fixture(scope="module")
def test_datasource_module(
    db_session_module,
    tmp_path_factory,
    datasource_template_file: Path,
):
    """Module-scoped SQLite datasource.

    Use in test classes that treat the test database as read-only or
    whose modifications don't conflict within the same module.
    Saves ~0.5 s of DB-init overhead per additional test.
    """
    db_dir = tmp_path_factory.mktemp("ds_module")
    return _make_datasource(
        db_session_module,
        db_dir,
        datasource_template_file,
        ds_id="ds-test-module",
    )



