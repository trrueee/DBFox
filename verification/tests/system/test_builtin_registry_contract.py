"""Contracts for the Kernel-owned default Tool Registry.

System DLC tools are intentionally absent until their signed package is
enabled and compiled into a RuntimeContributionSnapshot.
"""

from __future__ import annotations

import pytest

from engine.runtime_composition import build_product_tool_registry
from engine.tools.materialization import materialize_tools
from engine.tools.runtime import ToolAdmissionDecision, ToolKey, ToolRegistry
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


# The Turn snapshot freezes both the strict wire schema and the declared inputs.
FROZEN_MATERIALIZATION_HASH = (
    "9c34e81ecedf3a8cfcfc70f70a3f7fbd5b94607a96ebbcf68f717bef7add5a73"
)

FROZEN_BUILTIN_NAMES = (
    "conversation_read",
    "conversation_search",
    "project_resource_search",
    "request_clarification",
    "submit_answer",
    "update_plan",
)

FROZEN_OWNERS = {
    "request_clarification": "dbfox.core",
    "submit_answer": "dbfox.core",
    "update_plan": "dbfox.core",
    "project_resource_search": "dbfox.core",
    "conversation_read": "dbfox.conversation",
    "conversation_search": "dbfox.conversation",
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


def test_same_local_name_from_distinct_owners_is_composable() -> None:
    first = _EchoTool()
    second = _EchoTool()
    registry = (
        ToolRegistry()
        .register(first, owner="acme.files")
        .register(second, owner="other.workspace")
    )

    first_key = ToolKey("acme.files", "tests_echo")
    second_key = ToolKey("other.workspace", "tests_echo")
    assert registry.require_key(first_key) is first
    assert registry.require_key(second_key) is second
    assert registry.provider_name_for_key(first_key) != registry.provider_name_for_key(second_key)
    assert len(registry.tool_names()) == 2


def test_invalid_owner_id_is_rejected() -> None:
    registry = ToolRegistry()
    with pytest.raises(ValueError, match="owner ID"):
        registry.register(_EchoTool(), owner="DBFox.Data")


def test_registry_copy_preserves_authority_and_isolates_staging() -> None:
    class ProcessTool(_EchoTool):
        name = "process"
        policy = ToolPolicy(requires_admission=True, requires_approval=True)
        execution = ToolExecutionSpec(capabilities=("subprocess",))

        def admit(self, input, context):
            return ToolAdmissionDecision(status="blocked", risk_level="danger", reason="Not executed by this registry test")

    class IsolatedTool(_EchoTool):
        name = "isolated"
        execution = ToolExecutionSpec(backend="isolated_process", capabilities=("filesystem_write",))

    tool = ProcessTool()
    base = ToolRegistry(available_backends=frozenset({"in_process", "isolated_process"}))
    base.register(tool, owner="dbfox.tests", package_digest="digest", provider_name="explicit_name", host_supervised_process=True)
    base.freeze()
    staged = base.copy()
    assert not staged.frozen and base.frozen
    assert staged.require("explicit_name") is tool
    assert staged.host_supervises_process("explicit_name")
    assert staged.implementation_identity_of("explicit_name") == base.implementation_identity_of("explicit_name")
    staged.register(IsolatedTool(), owner="dbfox.tests")
    assert len(staged) == 2 and len(base) == 1
    assert staged.key_of(tool) == base.key_of(tool)


def test_semantic_capability_requires_namespaced_ids() -> None:
    from engine.tools.runtime.semantics import ToolSemanticSpec

    with pytest.raises(ValueError, match="namespaced ID"):
        ToolSemanticSpec(produces=("query_result",))
    namespaced = ToolSemanticSpec(produces=("dbfox.workspace.file_snapshot",))
    assert namespaced.produces == ("dbfox.workspace.file_snapshot",)
