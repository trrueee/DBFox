"""Capability-neutral Resource prerequisite and frozen-authority contracts."""

from __future__ import annotations

import pytest

from engine.agent.tool_dispatcher import ToolRequest
from engine.errors import ToolInputError
from engine.resource import ResourceScopeRef
from engine.tools.materialization import current_tool_contract_hash, materialize_tools
from engine.tools.runtime import (
    BaseTool,
    ToolExecutionSpec,
    ToolInputModel,
    ToolOutputModel,
    ToolPresentation,
    ToolRegistry,
    ToolRunContext,
)
from engine.tools.runtime.attempt import CompositeResourceResolver
from engine.tools.runtime.resource_context import build_tool_scope_context


class ProbeInput(ToolInputModel):
    value: str = ""


class ProbeOutput(ToolOutputModel):
    value: str = ""


class FreeProbe(BaseTool[ProbeInput, ProbeOutput]):
    name = "verification_free"
    group = "verification"
    description = "Probe a resource-free Core tool contract."
    input_model = ProbeInput
    output_model = ProbeOutput
    presentation = ToolPresentation(title="Free probe", category="explore")

    def run(self, tool_input: ProbeInput, context: ToolRunContext) -> ProbeOutput:
        del context
        return ProbeOutput(value=tool_input.value)


class AlphaProbe(FreeProbe):
    name = "verification_alpha"
    execution = ToolExecutionSpec(required_resource_kinds=("verification.alpha",))


class BetaProbe(FreeProbe):
    name = "verification_beta"
    execution = ToolExecutionSpec(required_resource_kinds=("verification.beta",))


def _registry() -> ToolRegistry:
    return ToolRegistry().register(FreeProbe()).register(AlphaProbe()).register(BetaProbe())


@pytest.mark.parametrize(
    ("available", "expected"),
    [
        (frozenset(), {"verification_free"}),
        (frozenset({"verification.alpha"}), {"verification_free", "verification_alpha"}),
        (frozenset({"verification.beta"}), {"verification_free", "verification_beta"}),
        (
            frozenset({"verification.alpha", "verification.beta"}),
            {"verification_free", "verification_alpha", "verification_beta"},
        ),
    ],
)
def test_materialization_filters_by_available_resource_kinds(available, expected):
    materialized = materialize_tools(
        _registry(),
        execution_mode="agent_autonomous_read",
        available_resource_kinds=available,
    )
    assert {tool.name for tool in materialized.tools} == expected


def test_none_resource_filter_is_explicitly_unconstrained():
    materialized = materialize_tools(
        _registry(),
        execution_mode="agent_autonomous_read",
        available_resource_kinds=None,
    )
    assert {tool.name for tool in materialized.tools} == {
        "verification_free",
        "verification_alpha",
        "verification_beta",
    }


def test_resource_requirement_and_host_capability_are_orthogonal():
    class FilesystemProbe(FreeProbe):
        name = "verification_filesystem"
        execution = ToolExecutionSpec(capabilities=("filesystem_read",))

    materialized = materialize_tools(
        ToolRegistry().register(FilesystemProbe()),
        execution_mode="agent_autonomous_read",
        available_resource_kinds=frozenset(),
    )
    assert [tool.name for tool in materialized.tools] == ["verification_filesystem"]


def test_scope_resolution_preserves_multiple_same_kind_resource_keys(db_session):
    first = ResourceScopeRef(kind="verification.alpha", id="one", version=1)
    second = ResourceScopeRef(kind="verification.alpha", id="two", version=2)
    resolver = CompositeResourceResolver().register(
        "verification.alpha", lambda ref: {"resolved": ref.id}
    ).freeze()
    request = ToolRequest(
        question="probe",
        session_id="session",
        run_id="run",
        execution_mode="agent_autonomous_read",
        frozen_resource_refs=(first, second),
    )
    scopes, resources = build_tool_scope_context(
        db_session, request, AlphaProbe(), resolver
    )
    assert scopes == (first, second)
    assert resources[first.canonical()] == {"resolved": "one"}
    assert resources[second.canonical()] == {"resolved": "two"}


def test_missing_frozen_resource_fails_closed(db_session):
    request = ToolRequest(
        question="probe",
        session_id="session",
        run_id="run",
        execution_mode="agent_autonomous_read",
        frozen_resource_refs=(),
    )
    with pytest.raises(ToolInputError, match="verification.alpha"):
        build_tool_scope_context(
            db_session,
            request,
            AlphaProbe(),
            CompositeResourceResolver().freeze(),
        )


def test_required_resource_kind_is_part_of_frozen_tool_contract():
    class ChangedProbe(FreeProbe):
        name = "verification_alpha"
        execution = ToolExecutionSpec(required_resource_kinds=("verification.alpha",))

    assert current_tool_contract_hash(FreeProbe()) != current_tool_contract_hash(ChangedProbe())


def test_required_resource_kind_validation():
    with pytest.raises(ValueError, match="namespaced identifier"):
        ToolExecutionSpec(required_resource_kinds=("",))
    with pytest.raises(ValueError, match="duplicates"):
        ToolExecutionSpec(required_resource_kinds=("verification.alpha", "verification.alpha"))
