"""Contracts for the Kernel-owned default Tool Registry.

System DLC tools are intentionally absent until their signed package is
enabled and compiled into a RuntimeContributionSnapshot.
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
    "bd34c525cfca439f04997c46203e14f3225cf848ede7301da5e7a04bdb17d789"
)

FROZEN_BUILTIN_NAMES = (
    "conversation_read",
    "conversation_search",
    "remote_job_cancel",
    "remote_job_status",
    "remote_job_submit",
    "request_clarification",
    "update_plan",
)

FROZEN_OWNERS = {
    "request_clarification": "dbfox.core",
    "update_plan": "dbfox.core",
    "conversation_read": "dbfox.conversation",
    "conversation_search": "dbfox.conversation",
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


def test_semantic_capability_requires_namespaced_ids() -> None:
    from engine.tools.runtime.semantics import ToolSemanticSpec

    with pytest.raises(ValueError, match="namespaced ID"):
        ToolSemanticSpec(produces=("query_result",))
    namespaced = ToolSemanticSpec(produces=("dbfox.workspace.file_snapshot",))
    assert namespaced.produces == ("dbfox.workspace.file_snapshot",)
