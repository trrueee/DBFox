from __future__ import annotations

import ast
from pathlib import Path

from engine.db import Base


ROOT = Path(__file__).resolve().parents[1]
REMOVED_MODULE_PREFIXES = (
    "engine.agent_core", "engine.agent_runtime", "engine.agent.graph", "engine.agent.nodes",
    "langgraph", "langchain", "langchain_openai", "langchain_core",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.add(node.module)
    return values


def test_product_code_has_no_removed_agent_or_graph_dependencies():
    violations: list[str] = []
    for path in ROOT.rglob("*.py"):
        if "migrations" in path.parts or "tests" in path.parts:
            continue
        for imported in _imports(path):
            if imported.startswith(REMOVED_MODULE_PREFIXES):
                violations.append(f"{path.relative_to(ROOT)} -> {imported}")
    assert violations == []


def test_metadata_exposes_one_agent_source_of_truth():
    names = set(Base.metadata.tables)
    assert {
        "agent_sessions", "agent_session_inputs", "agent_messages", "agent_runs", "agent_turns",
        "agent_tool_invocations", "agent_observations", "agent_approvals", "agent_question_requests",
        "agent_artifacts", "agent_evidence", "agent_events",
    } <= names
    assert not any(name.startswith("agent_runtime_") for name in names)
    assert {"agent_checkpoints", "agent_trace_events"}.isdisjoint(names)


def test_public_api_has_no_legacy_agent_run_router():
    source = (ROOT / "api" / "__init__.py").read_text(encoding="utf-8")
    assert "agent_runtime" not in source
