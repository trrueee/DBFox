from __future__ import annotations

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
        "datasource_id": "datasource-1",
        "datasource_generation": 1,
        "environment_profile": {"env": "dev"},
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


def test_update_plan_empty_call_reports_missing_required_fields(db_session):
    decision = PolicyGate(build_product_tool_registry(), db_session).check(
        _state(allowed_tool_groups=["manage"]),
        "update_plan",
        {},
    )

    assert decision.status == "blocked"
    assert "objective (missing)" in decision.reason
    assert "steps (missing)" in decision.reason


def test_schema_list_empty_arguments_apply_canonical_model_defaults(db_session):
    decision = PolicyGate(build_product_tool_registry(), db_session).check(
        _state(allowed_tool_groups=["catalog"]),
        "schema_list",
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
    registry = ToolRegistry().register(
        PolicyTestTool(policy=ToolPolicy(requires_approval=True))
    )
    decision = PolicyGate(registry, db_session).check(
        _state(),
        "policy_test",
        {},
    )
    assert decision.status == "approval_required"


def test_autonomous_database_read_requires_approval_on_unknown_environment(
    db_session,
):
    registry = ToolRegistry().register(
        PolicyTestTool(
            execution=ToolExecutionSpec(capabilities=("database_read",))
        )
    )
    decision = PolicyGate(registry, db_session).check(
        _state(environment_profile={"env": "unknown"}),
        "policy_test",
        {},
        "agent_autonomous_read",
    )
    assert decision.status == "approval_required"


def test_tool_admission_requires_an_exact_current_run_artifact(db_session):
    registry = ToolRegistry().register(ArtifactAdmissionTestTool())
    decision = PolicyGate(registry, db_session).check(
        _state(),
        "artifact_admission_test",
        {"validation_artifact_id": "artifact_missing"},
    )
    assert decision.status == "blocked"
    assert "current Run" in decision.reason
