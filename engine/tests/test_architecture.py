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
                               "skills", "context_pack", "extensions", "memory_bridge", "repair")}
    assert not unexpected, (
        f"engine.agent exports unexpected names: {unexpected}. "
        f"Public types belong in engine.agent_core."
    )


def test_agent_core_exports_public_contracts() -> None:
    """engine.agent_core must export ToolRegistry, types, persistence."""
    agent_core = importlib.import_module("engine.agent_core")
    assert hasattr(agent_core, "ToolRegistry"), "agent_core must export ToolRegistry"
    assert hasattr(agent_core, "ToolSpec"), "agent_core must export ToolSpec"
    assert hasattr(agent_core, "ToolPolicy"), "agent_core must export ToolPolicy"
    assert hasattr(agent_core, "AgentRunRequest"), "agent_core must export AgentRunRequest"
    assert hasattr(agent_core, "persistence"), "agent_core must export persistence"
    # CRITICAL: agent_core must NOT export DBFoxAgentRuntime
    assert not hasattr(agent_core, "DBFoxAgentRuntime"), (
        "agent_core must NOT export DBFoxAgentRuntime (it belongs in engine.agent)"
    )
