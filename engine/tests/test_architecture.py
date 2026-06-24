"""Architecture constraint tests — prevent dependency direction violations.

These tests encode the project's dependency rules as executable checks.
If any test fails, a module has introduced a forbidden import.
"""

from __future__ import annotations

import ast
import importlib
import os
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent  # engine/


def _imports_in_file(filepath: Path) -> list[str]:
    """Return the set of top-level module targets imported by a .py file."""
    if not filepath.exists():
        return []
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                targets.append(node.module)
    return targets


def _imports_in_package(pkg_dir: Path) -> set[str]:
    """Return the union of all imported module targets in a package."""
    all_imports: set[str] = set()
    for py_file in pkg_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        all_imports.update(_imports_in_file(py_file))
    return all_imports


# ---------------------------------------------------------------------------
# PACKAGE-LEVEL CONSTRAINT TESTS
# ---------------------------------------------------------------------------


def test_agent_core_does_not_import_agent() -> None:
    """agent_core MUST NOT depend on agent (runtime)."""
    imports = _imports_in_package(ENGINE_DIR / "agent_core")
    violations = [i for i in imports if i.startswith("engine.agent") and not i.startswith("engine.agent_core")]
    assert not violations, f"agent_core imports agent: {violations}"


def test_semantic_does_not_import_agent() -> None:
    """semantic MUST NOT depend on agent runtime."""
    imports = _imports_in_package(ENGINE_DIR / "semantic")
    violations = [i for i in imports if i.startswith("engine.agent") and not i.startswith("engine.agent_core")]
    assert not violations, f"semantic imports agent: {violations}"


def test_environment_does_not_import_agent() -> None:
    """environment MUST NOT depend on agent runtime."""
    imports = _imports_in_package(ENGINE_DIR / "environment")
    violations = [i for i in imports if i.startswith("engine.agent") and not i.startswith("engine.agent_core")]
    assert not violations, f"environment imports agent: {violations}"


def test_sql_does_not_import_agent() -> None:
    """sql MUST NOT depend on agent runtime."""
    imports = _imports_in_package(ENGINE_DIR / "sql")
    violations = [i for i in imports if i.startswith("engine.agent") and not i.startswith("engine.agent_core")]
    assert not violations, f"sql imports agent: {violations}"


def test_tools_do_not_import_agent_runtime() -> None:
    """tools MUST NOT import anything from engine.agent (runtime).

    engine.agent_core is the only allowed agent-adjacent import.
    engine.agent.* is forbidden — tools depend on domain services:
      engine.memory, engine.policy, engine.environment, engine.semantic, engine.sql, engine.llm.
    """
    imports = _imports_in_package(ENGINE_DIR / "tools")
    violations = [i for i in imports
                  if i.startswith("engine.agent")
                  and not i.startswith("engine.agent_core")]
    assert not violations, f"tools import engine.agent (runtime): {violations}"


def test_no_old_registry_imports() -> None:
    """No file should import from the deleted engine.agent_core.registry."""
    for dirname in ["agent", "agent_core", "tools", "tests", "api", "evaluation"]:
        pkg = ENGINE_DIR / dirname
        if not pkg.exists():
            continue
        imports = _imports_in_package(pkg)
        violations = [i for i in imports if i == "engine.agent_core.registry"]
        assert not violations, f"{dirname} still imports old registry: {violations}"


def test_no_agent_persistence_imports() -> None:
    """No file should import from the deleted engine.agent.persistence."""
    for dirname in ["agent", "agent_core", "tools", "tests", "api", "evaluation"]:
        pkg = ENGINE_DIR / dirname
        if not pkg.exists():
            continue
        imports = _imports_in_package(pkg)
        violations = [i for i in imports if i == "engine.agent.persistence"]
        assert not violations, f"{dirname} still imports engine.agent.persistence: {violations}"


def test_no_legacy_long_term_memory_imports() -> None:
    """Runtime memory uses graph projection + reusable SQL, not old long-term memory."""
    forbidden = {
        "engine.agent.memory_bridge",
        "engine.memory.long_term_store",
        "engine.memory.memory_namespace",
        "engine.memory.memory_policy",
        "engine.memory.memory_retriever",
        "engine.memory.memory_schema",
        "engine.memory.memory_writer",
        "engine.memory.session_memory",
    }
    for dirname in ["agent", "agent_core", "tools", "environment", "tests", "api", "evaluation"]:
        pkg = ENGINE_DIR / dirname
        if not pkg.exists():
            continue
        imports = _imports_in_package(pkg)
        violations = sorted(forbidden & imports)
        assert not violations, f"{dirname} imports legacy long-term memory modules: {violations}"


def test_agent_state_declares_each_field_once() -> None:
    """DBFoxAgentState should not silently override TypedDict fields."""
    filepath = ENGINE_DIR / "agent" / "graph" / "state.py"
    tree = ast.parse(filepath.read_text(encoding="utf-8"))
    state_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "DBFoxAgentState"
    )
    counts: dict[str, int] = {}
    for node in state_class.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            counts[node.target.id] = counts.get(node.target.id, 0) + 1

    duplicates = sorted(name for name, count in counts.items() if count > 1)
    assert not duplicates, f"DBFoxAgentState declares duplicate fields: {duplicates}"


def test_sql_lifecycle_tools_have_one_model_visible_path() -> None:
    """Model-authored SQL must use validate -> execute, while db.query stays internal."""
    from engine.agent.model.system_prompt import SYSTEM_PROMPT
    from engine.tools.dbfox_tools import register_dbfox_tools

    registry = register_dbfox_tools()
    db_query = registry.require("db.query").spec
    validate = registry.require("sql.validate").spec
    execute = registry.require("sql.execute_readonly").spec

    assert db_query.policy.visible_to_model is False
    assert validate.policy.visible_to_model is True
    assert execute.policy.visible_to_model is True
    assert execute.policy.requires_validated_sql is True
    assert "db.query is an internal backend fast path" in SYSTEM_PROMPT
    assert "sql.validate" in SYSTEM_PROMPT
    assert "sql.execute_readonly" in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# __init__.py PUBLIC API TESTS
# ---------------------------------------------------------------------------


def test_engine_agent_init_exports_runtime_only() -> None:
    """engine.agent.__init__ must only export runtime classes."""
    agent = importlib.import_module("engine.agent")
    public = [n for n in dir(agent) if not n.startswith("_")]
    # Allowed public API
    allowed = {"DBFoxAgentRuntime", "DBFoxAgentService", "build_dbfox_react_graph"}
    unexpected = set(public) - allowed
    # Filter out subpackages and module internals
    unexpected = {u for u in unexpected
                  if u not in ("annotations", "app", "graph", "nodes", "planning",
                               "progress", "guardrails", "model", "tools", "runtime",
                               "checkpoints", "environment", "events", "memory", "tests",
                               "skills", "context_pack", "extensions", "repair")}
    assert not unexpected, (
        f"engine.agent exports unexpected names: {unexpected}. "
        f"Public types belong in engine.agent_core."
    )


def test_agent_core_exports_public_contracts() -> None:
    """engine.agent_core exports data contracts, not tool runtime classes."""
    agent_core = importlib.import_module("engine.agent_core")
    assert hasattr(agent_core, "AgentRunRequest"), "agent_core must export AgentRunRequest"
    assert hasattr(agent_core, "persistence"), "agent_core must export persistence"
    assert not hasattr(agent_core, "ToolRegistry"), "tool runtime belongs in engine.tools.runtime"
    assert not hasattr(agent_core, "ToolSpec"), "tool runtime belongs in engine.tools.runtime"
    assert not hasattr(agent_core, "ToolPolicy"), "tool runtime belongs in engine.tools.runtime"
    # CRITICAL: agent_core must NOT export DBFoxAgentRuntime
    assert not hasattr(agent_core, "DBFoxAgentRuntime"), (
        "agent_core must NOT export DBFoxAgentRuntime (it belongs in engine.agent)"
    )
