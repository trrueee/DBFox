"""Shared pytest fixtures for DataBox engine tests."""
import os
os.environ["DATABOX_BYPASS_CONFIRMATION"] = "1"
os.environ["DATABOX_TESTING"] = "1"

# ---- LLM provider defaults for testing --------------------------------------
# When a QWEN_API_KEY is set, auto-configure the OpenAI-compatible endpoint.
_qwen_key = os.environ.get("QWEN_API_KEY", "").strip()
if _qwen_key:
    os.environ.setdefault("OPENAI_API_KEY", _qwen_key)
    os.environ.setdefault("OPENAI_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    os.environ.setdefault("OPENAI_MODEL_NAME", "qwen-plus")

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


@pytest.fixture
def test_datasource(db_session, tmp_path):
    """Isolated SQLite datasource for integration tests (tmp file, not production DB)."""
    db_file = tmp_path / "test_engine.db"
    db_path = _init_test_db(str(db_file))

    ds = DataSource(
        id=str(uuid.uuid4()),
        name="test_sqlite",
        host="localhost",
        port=0,
        database_name=db_path,
        username="test",
        password_ciphertext="test",
        password_nonce="test",
        db_type="sqlite",
        status="active",
    )
    db_session.add(ds)
    db_session.commit()
    return ds


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
def mock_agent_progress_judge(monkeypatch):
    """Progress Judge requires LLM credentials; without real keys use the
    module's rule-based fallback (mirrors the legacy routing logic)."""
    import os
    if os.environ.get("DATABOX_LLM_API_KEY") or os.environ.get("QWEN_API_KEY") or os.environ.get("OPENAI_API_KEY"):
        return

    from engine.agent.nodes import progress_node

    def fake_judge_progress(state, config):
        escalate_result = progress_node._check_escalate(state)
        if escalate_result:
            return escalate_result
        return progress_node._rule_fallback(state)

    monkeypatch.setattr(progress_node, "judge_progress", fake_judge_progress)


@pytest.fixture(autouse=True)
def mock_agent_call_model(monkeypatch):
    import os
    if os.environ.get("DATABOX_LLM_API_KEY") or os.environ.get("QWEN_API_KEY") or os.environ.get("OPENAI_API_KEY"):
        return

    from engine.agent.nodes import model_node
    from langchain_core.messages import AIMessage
    import uuid

    def mock_call_model(state, config):
        step_count = int(state.get("step_count", 0))
        max_steps = int(state.get("max_steps", 20))
        if step_count >= max_steps:
            if not state.get("safety"):
                err = "Agent stopped before SQL validation because max_steps was reached."
            else:
                err = f"Agent exceeded max_steps ({max_steps})."
            return {
                "status": "failed",
                "error": err,
                "trace_events": [
                    {
                        "type": "agent.max_steps_exceeded",
                        "step_count": step_count,
                        "max_steps": max_steps,
                    }
                ],
            }

        messages = state.get("messages") or []
        question = state.get("question")
        if not question:
            for msg in messages:
                if isinstance(msg, dict):
                    if msg.get("role") == "user":
                        question = msg.get("content")
                        break
                else:
                    if getattr(msg, "type", None) == "human" or msg.__class__.__name__ in ("HumanMessage", "UserMessage"):
                        question = getattr(msg, "content", "")
                        break
        question = question or ""

        called_tools = []
        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role") or msg.get("type")
                if role == "tool":
                    called_tools.append(msg.get("name"))
            else:
                if getattr(msg, "type", None) == "tool" or msg.__class__.__name__ == "ToolMessage":
                    called_tools.append(getattr(msg, "name", None))

        next_tool = None
        workspace_context = state.get("workspace_context")

        if workspace_context:
            has_workspace_run = any(
                t in called_tools 
                for t in ["workspace_explain_sql", "workspace_fix_sql", "workspace_optimize_sql", 
                          "workspace_rewrite_sql", "workspace_explain_result", "workspace_explain_schema"]
            )
            if not has_workspace_run:
                question_lower = question.lower()
                if "fix" in question_lower or "error" in question_lower:
                    next_tool = "workspace_fix_sql"
                elif "optimize" in question_lower:
                    next_tool = "workspace_optimize_sql"
                elif "explain" in question_lower:
                    if "result" in question_lower:
                        next_tool = "workspace_explain_result"
                    elif "schema" in question_lower:
                        next_tool = "workspace_explain_schema"
                    else:
                        next_tool = "workspace_explain_sql"
                else:
                    next_tool = "workspace_explain_sql"
        else:
            has_follow_up = state.get("follow_up_context") is not None
            
            if has_follow_up and "followup_load_context" not in called_tools:
                next_tool = "followup_load_context"
            elif "schema_build_context" not in called_tools:
                next_tool = "schema_build_context"
            elif "sql_generate" not in called_tools:
                next_tool = "sql_generate"
            elif "sql_validate" not in called_tools:
                next_tool = "sql_validate"
            elif "sql_execute_readonly" not in called_tools and "sql_skip_execution" not in called_tools:
                safety = state.get("safety") or {}
                blocked = safety.get("blocked_reasons") or []
                hard_blocked = any(r != "requires_confirmation" for r in blocked)
                if safety and hard_blocked:
                    if "sql_revise" not in called_tools:
                        next_tool = "sql_revise"
                else:
                    print(f"\n[DEBUG MOCK LLM] state.get('execute')={state.get('execute')}, keys={list(state.keys())}")
                    if state.get("execute"):
                        next_tool = "sql_execute_readonly"
                    else:
                        next_tool = "sql_skip_execution"
            elif "result_profile" not in called_tools:
                execution = state.get("execution")
                if execution and "success" in execution and not execution.get("success"):
                    if "sql_revise" not in called_tools:
                        next_tool = "sql_revise"
                else:
                    next_tool = "result_profile"
            elif "chart_suggest" not in called_tools:
                next_tool = "chart_suggest"
            elif "followup_suggest" not in called_tools:
                next_tool = "followup_suggest"
            elif "answer_synthesize" not in called_tools:
                next_tool = "answer_synthesize"

        if next_tool is None:
            # Complete
            answer_raw = state.get("answer") or {}
            if isinstance(answer_raw, dict):
                ans_text = answer_raw.get("answer") or "Here is the final answer."
            else:
                ans_text = str(answer_raw or "Here is the final answer.")
            
            ai_msg = AIMessage(content=ans_text)
            
            status = "completed"
            error = None
            safety = state.get("safety")
            if safety:
                blocked = safety.get("blocked_reasons") or []
                hard_blocked = any(r != "requires_confirmation" for r in blocked)
                if hard_blocked:
                    status = "failed"
                    error = "SQL validation failed."
            execution = state.get("execution")
            if execution and "success" in execution and not execution.get("success"):
                status = "failed"
                error = execution.get("error") or "Query execution failed."

            return {
                "messages": [ai_msg],
                "status": status,
                "error": error,
                "trace_events": [
                    {
                        "type": "agent.model.completed",
                        "tool_calls": [],
                    }
                ],
                "step_count": step_count + 1,
            }
        else:
            # Call tool
            tool_args = {}
            if next_tool == "schema_build_context":
                tool_args = {"question": question}
            elif next_tool == "sql_generate":
                tool_args = {"question": question}
            elif next_tool in ("sql_validate", "sql_execute_readonly", "sql_skip_execution", "sql_revise"):
                tool_args = {"sql": state.get("sql")}

            tool_call = {
                "name": next_tool,
                "args": tool_args,
                "id": f"call_{uuid.uuid4().hex[:12]}",
                "type": "tool_call",
            }
            ai_msg = AIMessage(content="", tool_calls=[tool_call])
            return {
                "messages": [ai_msg],
                "trace_events": [
                    {
                        "type": "agent.model.completed",
                        "tool_calls": [tool_call],
                    }
                ],
                "step_count": step_count + 1,
            }

    monkeypatch.setattr(model_node, "call_model", mock_call_model)

