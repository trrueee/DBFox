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
                safety = state.get("safety")
                if safety and not safety.get("can_execute"):
                    if "sql_revise" not in called_tools:
                        next_tool = "sql_revise"
                else:
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
            if safety and not safety.get("can_execute"):
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

