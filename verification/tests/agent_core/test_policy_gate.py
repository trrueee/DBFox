from __future__ import annotations

import pytest

from engine.policy.gate import PolicyGate
from engine.runtime_composition import build_product_tool_registry
from engine.tools.runtime import (
    BaseTool,
    ToolAdmissionContext,
    ToolAdmissionDecision,
    ToolExecutionSpec,
    ToolInputModel,
    ToolOutputModel,
    ToolPolicy,
    ToolPresentation,
    ToolRegistry,
)
from verification.support.agent_tools import verification_registry


class PolicyInput(ToolInputModel):
    value: int | None = None
    validation_artifact_id: str | None = None


class PolicyOutput(ToolOutputModel):
    ok: bool


class PolicyTestTool(BaseTool[PolicyInput, PolicyOutput]):
    name = "policy_test"
    group = "test"
    description = "Exercise the generic policy boundary."
    input_model = PolicyInput
    output_model = PolicyOutput
    presentation = ToolPresentation(
        title="Policy test",
        category="manage",
        visibility="developer",
    )

    def __init__(
        self,
        *,
        name: str = "policy_test",
        policy: ToolPolicy | None = None,
        execution: ToolExecutionSpec | None = None,
    ) -> None:
        self.name = name
        self.policy = policy or ToolPolicy()
        self.execution = execution or ToolExecutionSpec()

    def run(self, tool_input, context):
        return PolicyOutput(ok=True)


class ArtifactAdmissionTestTool(BaseTool[PolicyInput, PolicyOutput]):
    name = "artifact_admission_test"
    group = "test"
    description = "Exercise fail-closed Artifact admission."
    input_model = PolicyInput
    output_model = PolicyOutput
    policy = ToolPolicy(requires_admission=True)
    presentation = ToolPresentation(
        title="Artifact admission test",
        category="manage",
        visibility="developer",
    )

    def admit(
        self,
        tool_input: PolicyInput,
        context: ToolAdmissionContext,
    ) -> ToolAdmissionDecision:
        try:
            context.artifact(tool_input.validation_artifact_id or "")
        except RuntimeError:
            return ToolAdmissionDecision(
                status="blocked",
                reason="The required Artifact is unavailable in the current Run.",
                risk_level="danger",
            )
        return ToolAdmissionDecision(status="allowed", reason="Artifact is current.")

    def run(self, tool_input, context):
        return PolicyOutput(ok=True)


def _state(**overrides):
    return {
        "session_id": "session-1",
        "run_id": "run-1",
        "allowed_tool_groups": ["test"],
        **overrides,
    }


def test_unknown_function_is_blocked(db_session):
    decision = PolicyGate(ToolRegistry(), db_session).check(
        _state(),
        "missing_function",
        {},
    )
    assert decision.status == "blocked"
    assert decision.error_code is None


def test_safe_metadata_tool_is_allowed(db_session):
    registry = ToolRegistry().register(PolicyTestTool())
    decision = PolicyGate(registry, db_session).check(
        _state(),
        "policy_test",
        {"value": 1},
    )
    assert decision.status == "allowed"
    assert decision.safe_args == {"value": 1}


def test_input_contract_is_enforced_before_policy_rules(db_session):
    registry = ToolRegistry().register(PolicyTestTool())
    decision = PolicyGate(registry, db_session).check(
        _state(),
        "policy_test",
        {"unexpected": True},
    )
    assert decision.status == "blocked"
    assert decision.error_code == "TOOL_INPUT_INVALID"
    assert "input contract" in decision.reason


def test_input_contract_reason_names_schema_locations_without_reflecting_values(
    db_session,
):
    registry = ToolRegistry().register(PolicyTestTool())
    decision = PolicyGate(registry, db_session).check(
        _state(),
        "policy_test",
        {"value": "TOP_SECRET_SENTINEL"},
    )

    assert decision.status == "blocked"
    assert "value (int_parsing)" in decision.reason
    assert "TOP_SECRET_SENTINEL" not in decision.reason


@pytest.mark.parametrize("unknown_field", ["SECRET_FIELD_SENTINEL", "x" * 10000], ids=["unknown", "oversized"])
def test_input_diagnostics_do_not_reflect_unknown_keys_or_grow_with_them(db_session, unknown_field):
    decision = PolicyGate(ToolRegistry().register(PolicyTestTool()), db_session).check(
        _state(), "policy_test", {unknown_field: "PRIVATE_VALUE"},
    )
    assert decision.status == "blocked"
    assert unknown_field not in decision.reason
    assert "PRIVATE_VALUE" not in decision.reason
    assert "extra_forbidden" in decision.reason
    assert len(decision.reason) <= 2048


def test_input_diagnostics_keep_declared_nested_locations_but_not_dynamic_keys(db_session):
    from engine.tools.builtin.control import SubmitAnswerCommand

    registry = ToolRegistry().register(SubmitAnswerCommand())
    decision = PolicyGate(registry, db_session).check(
        _state(), "submit_answer",
        {"parts": [{"text": "PRIVATE_BODY", "citations": [123], "SECRET_NESTED_KEY": True}]},
    )
    assert "parts.0.citations.0 (string_type)" in decision.reason
    assert "SECRET_NESTED_KEY" not in decision.reason
    assert "PRIVATE_BODY" not in decision.reason


def test_input_diagnostics_preserve_schema_declared_discriminator_labels(db_session):
    from typing import Annotated, Literal
    from pydantic import Field

    class Append(ToolInputModel):
        operation: Literal["append"]
        amount: int

    class Remove(ToolInputModel):
        operation: Literal["remove"]
        position: int

    class ChangeInput(ToolInputModel):
        changes: list[Annotated[Append | Remove, Field(discriminator="operation")]]

    class ChangeTool(PolicyTestTool):
        input_model = ChangeInput

    decision = PolicyGate(ToolRegistry().register(ChangeTool()), db_session).check(
        _state(), "policy_test", {"changes": [{"operation": "append", "amount": "PRIVATE_VALUE"}]},
    )
    assert decision.status == "blocked"
    assert "changes.0.append.amount (int_parsing)" in decision.reason
    assert "PRIVATE_VALUE" not in decision.reason


def test_custom_validator_context_and_error_types_are_not_public_diagnostics(db_session):
    from pydantic import field_validator
    from pydantic_core import PydanticCustomError

    class PrivateInput(ToolInputModel):
        value: str

        @field_validator("value")
        @classmethod
        def reject(cls, value):
            raise PydanticCustomError(value, "PRIVATE_MESSAGE {secret}", {"secret": value})

    class PrivateTool(PolicyTestTool):
        input_model = PrivateInput

    decision = PolicyGate(ToolRegistry().register(PrivateTool()), db_session).check(
        _state(), "policy_test", {"value": "PRIVATE_DYNAMIC_TYPE"},
    )
    assert decision.status == "blocked"
    assert "value (invalid)" in decision.reason
    assert "PRIVATE_" not in decision.reason


def test_update_plan_empty_call_reports_missing_required_fields(db_session):
    decision = PolicyGate(build_product_tool_registry(), db_session).check(
        _state(allowed_tool_groups=["manage"]),
        "update_plan",
        {},
    )

    assert decision.status == "blocked"
    assert "objective (missing)" in decision.reason
    assert "steps (missing)" in decision.reason


def test_tool_empty_arguments_apply_canonical_model_defaults(db_session):
    decision = PolicyGate(verification_registry(), db_session).check(
        _state(allowed_tool_groups=["verification"]),
        "verification_read",
        {},
    )

    assert decision.status == "allowed"
    assert decision.safe_args == {"limit": 20}


def test_disallowed_group_is_blocked(db_session):
    registry = ToolRegistry().register(PolicyTestTool())
    decision = PolicyGate(registry, db_session).check(
        _state(allowed_tool_groups=["catalog"]),
        "policy_test",
        {},
    )
    assert decision.status == "blocked"


def test_declared_approval_requirement_is_preserved(db_session):
    tool = PolicyTestTool(policy=ToolPolicy(requires_approval=True))
    tool.presentation = ToolPresentation(title="编辑项目文件", category="manage")
    registry = ToolRegistry().register(tool)
    decision = PolicyGate(registry, db_session).check(
        _state(),
        "policy_test",
        {},
    )
    assert decision.status == "approval_required"
    assert decision.reason == "编辑项目文件需要你的批准。"
    assert "policy_test" not in decision.reason


@pytest.mark.parametrize(
    ("backend", "expected_status"),
    [("in_process", "blocked"), ("isolated_process", "approval_required")],
)
def test_subprocess_capability_requires_isolation_and_still_requires_approval(
    db_session, backend, expected_status,
):
    registry = ToolRegistry(
        available_backends=frozenset({"in_process", "isolated_process"})
    )
    tool = PolicyTestTool(
        execution=ToolExecutionSpec(backend=backend, capabilities=("subprocess",)),
        policy=ToolPolicy(requires_approval=True, risk_level="danger"),
    )
    if backend == "in_process":
        with pytest.raises(ValueError, match="require an isolated process"):
            registry.register(tool)
        return
    registry.register(tool)

    decision = PolicyGate(registry, db_session).check(_state(), "policy_test", {})

    assert decision.status == expected_status
    assert decision.risk_level == "danger"


def test_tool_admission_requires_an_exact_current_run_artifact(db_session):
    registry = ToolRegistry().register(ArtifactAdmissionTestTool())
    decision = PolicyGate(registry, db_session).check(
        _state(),
        "artifact_admission_test",
        {"validation_artifact_id": "artifact_missing"},
    )
    assert decision.status == "blocked"
    assert "current Run" in decision.reason
