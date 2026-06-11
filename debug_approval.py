import os
os.environ["DATABOX_BYPASS_CONFIRMATION"] = "1"
os.environ["DATABOX_TESTING"] = "1"

import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from engine.db import Base
from engine import models
from engine.models import DataSource
from engine.agent import DataBoxAgentRuntime
from engine.agent_core.types import AgentRunRequest
from engine.agent_core import persistence as agent_persistence
from engine.schema_sync import sync_schema

# Setup in-memory DB
engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(bind=engine)
db_session = SessionLocal()

# Setup datasource
demo_datasource = DataSource(
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
db_session.add(demo_datasource)
db_session.commit()

# Mock model call
from engine.agent.nodes import model_node
from langchain_core.messages import AIMessage

def mock_call_model(state, config):
    step_count = int(state.get("step_count", 0))
    messages = state.get("messages") or []
    called_tools = []
    for msg in messages:
        if isinstance(msg, dict):
            called_tools.append(msg.get("name"))
        elif msg.__class__.__name__ == "ToolMessage" or getattr(msg, "type", None) == "tool":
            called_tools.append(getattr(msg, "name", None))
    print(f"DEBUG mock_call_model: called_tools={called_tools}")

    next_tool = None
    if "schema_build_context" not in called_tools:
        next_tool = "schema_build_context"
    elif "sql_generate" not in called_tools:
        next_tool = "sql_generate"
    elif "sql_validate" not in called_tools:
        next_tool = "sql_validate"
    elif "sql_execute_readonly" not in called_tools:
        next_tool = "sql_execute_readonly"
    elif "answer_synthesize" not in called_tools:
        next_tool = "answer_synthesize"

    if next_tool is None:
        return {
            "messages": [AIMessage(content="done")],
            "status": "completed",
            "error": None,
            "step_count": step_count + 1,
        }
    else:
        tool_args = {}
        if next_tool == "schema_build_context":
            tool_args = {"question": "list users"}
        elif next_tool == "sql_generate":
            tool_args = {"question": "list users"}
        elif next_tool in ("sql_validate", "sql_execute_readonly"):
            tool_args = {"sql": state.get("sql")}
        
        tool_call = {
            "name": next_tool,
            "args": tool_args,
            "id": f"call_{uuid.uuid4().hex[:12]}",
            "type": "tool_call",
        }
        return {
            "messages": [AIMessage(content="", tool_calls=[tool_call])],
            "step_count": step_count + 1,
        }

from _pytest.monkeypatch import MonkeyPatch
mp = MonkeyPatch()
mp.setattr(model_node, "call_model", mock_call_model)

def _fake_select_sql(*_args, **_kwargs):
    return {
        "sql": "SELECT id, username FROM users LIMIT 3",
        "model": "test",
        "mode": "offline",
        "latencyMs": 1,
        "schemaValidationWarnings": [],
    }

sync_schema(db_session, demo_datasource.id)
demo_datasource.env = "prod"
db_session.commit()

mp.setattr("engine.tools.sql_tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)
mp.setattr("engine.tools.sql_tools.generate_sql_from_schema_context", _fake_select_sql)

print("Starting agent run...")
events = list(DataBoxAgentRuntime(db_session).run_iter(
    AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="list users",
        execute=True,
        session_id="approval-session",
    )
))

for ev in events:
    print(f"EVENT: {ev.type}")
    if ev.response:
        print(f"  status={ev.response.status}, success={ev.response.success}, error={ev.response.error}")
        if ev.response.steps:
            print(f"  steps={[s.name for s in ev.response.steps]}")
        if ev.response.safety:
            print(f"  safety={ev.response.safety}")

final = events[-1]
approval = agent_persistence.get_pending_approval_for_run(db_session, final.response.run_id)
print(f"APPROVAL: {approval}")
db_session.close()
