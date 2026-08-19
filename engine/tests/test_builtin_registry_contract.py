"""P0.5/P1 contracts for the built-in Tool Registry.

These tests freeze the current registration surface before extension ownership
changes, then prove that the owner-scoped composition path keeps the exact same
materialization contract.
"""

from __future__ import annotations

import pytest

from engine.runtime_composition import build_product_tool_registry
from engine.tools.materialization import materialize_tools
from engine.tools.runtime import ToolRegistry
from engine.tools.runtime.base import (
    BaseTool,
    ToolExecutionSpec,
    ToolInputModel,
    ToolOutputModel,
    ToolPolicy,
    ToolPresentation,
)


class _EchoInput(ToolInputModel):
    pass


class _EchoOutput(ToolOutputModel):
    pass


class _EchoTool(BaseTool[_EchoInput, _EchoOutput]):
    """Minimal stand-in for registry mutation tests only."""

    name = "tests_echo"
    group = "tests"
    description = "Registry mutation test tool."
    input_model = _EchoInput
    output_model = _EchoOutput
    presentation = ToolPresentation(title="Test", category="explore")
    policy = ToolPolicy()
    execution = ToolExecutionSpec(
        capabilities=("metadata_read",),
        concurrency="parallel_safe",
    )


FROZEN_MATERIALIZATION_HASH = (
    "58795b179bd303252ab0722764051dd9b9fb3ee92d94366e1493d5047d9fef85"
)

FROZEN_BUILTIN_NAMES = (
    "catalog_overview",
    "catalog_refresh",
    "chart_create",
    "conversation_read",
    "conversation_search",
    "data_preview",
    "file_read",
    "file_search",
    "file_write_patch",
    "remote_job_cancel",
    "remote_job_status",
    "remote_job_submit",
    "request_clarification",
    "result_inspect",
    "result_profile",
    "schema_inspect",
    "schema_list",
    "schema_search",
    "sql_execute_readonly",
    "sql_validate",
    "update_plan",
)

FROZEN_OWNERS = {
    "request_clarification": "dbfox.core",
    "update_plan": "dbfox.core",
    "conversation_read": "dbfox.conversation",
    "conversation_search": "dbfox.conversation",
    "catalog_overview": "dbfox.data",
    "catalog_refresh": "dbfox.data",
    "chart_create": "dbfox.data",
    "data_preview": "dbfox.data",
    "file_read": "dbfox.workspace",
    "file_search": "dbfox.workspace",
    "file_write_patch": "dbfox.workspace",
    "result_inspect": "dbfox.data",
    "result_profile": "dbfox.data",
    "schema_inspect": "dbfox.data",
    "schema_list": "dbfox.data",
    "schema_search": "dbfox.data",
    "sql_execute_readonly": "dbfox.data",
    "sql_validate": "dbfox.data",
    "remote_job_cancel": "dbfox.remote_job",
    "remote_job_status": "dbfox.remote_job",
    "remote_job_submit": "dbfox.remote_job",
}


def _materialization_hash(registry: ToolRegistry) -> str:
    return materialize_tools(
        registry,
        execution_mode="agent_autonomous_read",
    ).hash


def test_builtin_tool_names_are_frozen() -> None:
    registry = build_product_tool_registry()
    assert registry.tool_names() == FROZEN_BUILTIN_NAMES


def test_builtin_materialization_hash_is_frozen() -> None:
    assert _materialization_hash(build_product_tool_registry()) == FROZEN_MATERIALIZATION_HASH


def test_builtin_owner_partition_is_correct() -> None:
    registry = build_product_tool_registry()
    assert {name: registry.owner_of(name) for name in registry.tool_names()} == (
        FROZEN_OWNERS
    )
    assert set(FROZEN_OWNERS) == set(FROZEN_BUILTIN_NAMES)


def test_product_composition_returns_a_frozen_registry() -> None:
    registry = build_product_tool_registry()
    assert registry.frozen is True


def test_frozen_registry_rejects_late_registration() -> None:
    registry = ToolRegistry().freeze()
    with pytest.raises(RuntimeError, match="frozen"):
        registry.register(_EchoTool(), owner="dbfox.tests")


def test_duplicate_contribution_is_rejected() -> None:
    registry = ToolRegistry()
    registry.register(_EchoTool(), owner="dbfox.tests")
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_EchoTool(), owner="dbfox.tests")


def test_invalid_owner_id_is_rejected() -> None:
    registry = ToolRegistry()
    with pytest.raises(ValueError, match="owner ID"):
        registry.register(_EchoTool(), owner="DBFox.Data")


def test_semantic_capability_accepts_legacy_and_namespaced_ids() -> None:
    from engine.tools.runtime.semantics import ToolSemanticSpec

    legacy = ToolSemanticSpec(produces=("query_result",))
    namespaced = ToolSemanticSpec(produces=("dbfox.workspace.file_snapshot",))
    assert legacy.produces == ("query_result",)
    assert namespaced.produces == ("dbfox.workspace.file_snapshot",)
