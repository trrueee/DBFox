from __future__ import annotations

import json
import logging
import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest
from engine.agent.resource_refs import ProjectResourceDescriptor
from engine.errors import DBFoxError, ToolInputError
from engine.models import AgentSession, Project
from engine.tools.builtin.contracts import ProjectResourceSearchInput
from engine.tools.builtin.project_resources import ProjectResourceSearchTool
from engine.tools.runtime.base import (
    BaseTool,
    ToolExecutionSpec,
    ToolInputModel,
    ToolOutputModel,
    ToolPolicy,
    ToolPresentation,
    ToolRecoveryPolicy,
)
from engine.tools.runtime.context import ToolRunContext
from engine.tools.runtime.executor import ToolExecutor
from engine.tools.runtime.registry import ToolRegistry
from engine.tools.runtime.result import ToolReconciliation, ToolResult
from engine.tools.runtime.runtime import ToolRuntime


class EchoInput(ToolInputModel):
    value: str


class EchoOutput(ToolOutputModel):
    value: str
    seen: dict[str, Any]


class EchoTool(BaseTool[EchoInput, EchoOutput]):
    name = "test_echo"
    group = "test"
    description = "Echo a value."
    input_model = EchoInput
    output_model = EchoOutput
    presentation = ToolPresentation(title="Echo", category="manage", visibility="developer")
    policy = ToolPolicy()
    execution = ToolExecutionSpec()

    def run(self, tool_input: EchoInput, context: ToolRunContext) -> EchoOutput:
        return EchoOutput(
            value=tool_input.value,
            seen={"thread_id": context.thread_id},
        )


def test_tool_id_must_be_provider_neutral_at_definition_time():
    with pytest.raises(TypeError, match="same canonical Tool ID"):
        class InvalidTool(EchoTool):
            name = "schema.read"


def test_registry_and_provider_neutral_tool_spec():
    registry = ToolRegistry()
    registry.register(EchoTool())
    spec = registry.require("test_echo").spec
    assert spec.input_model is EchoInput
    assert spec.output_model is EchoOutput
    assert "langchain" not in type(registry).__module__


def test_registry_denies_privileged_capabilities_without_an_isolated_backend():
    class ProcessTool(EchoTool):
        name = "test_process"
        execution = ToolExecutionSpec(capabilities=("subprocess",))

    with pytest.raises(ValueError, match="require an isolated process"):
        ToolRegistry().register(ProcessTool())


def test_registry_preserves_the_declared_capability_contract():
    class ReadTool(EchoTool):
        name = "test_read"
        execution = ToolExecutionSpec(capabilities=("network",))

    registry = ToolRegistry().register(ReadTool())
    assert registry.require("test_read").spec.execution.capabilities == ("network",)


def test_registry_rejects_an_unavailable_execution_backend():
    class IsolatedTool(EchoTool):
        name = "test_isolated"
        execution = ToolExecutionSpec(
            backend="isolated_process",
            capabilities=("subprocess",),
        )

    with pytest.raises(ValueError, match="unavailable execution backend"):
        ToolRegistry().register(IsolatedTool())


def test_runtime_exposes_only_explicit_execution_context():
    registry = ToolRegistry()
    registry.register(EchoTool())
    result = ToolRuntime(registry).invoke(
        tool_name="test_echo", raw_input={"value": "hello"},
        request=SimpleNamespace(session_id="session-1"),
        idempotency_key="invocation-1",
    )
    assert result == ToolResult(
        name="test_echo", status="success", input={"value": "hello"},
        output={"value": "hello", "seen": {"thread_id": "session-1"}}, error=None,
        latency_ms=result.latency_ms,
    )


def test_runtime_reconciliation_receives_the_durable_idempotency_key():
    seen: list[str] = []

    class ReconcileTool(EchoTool):
        name = "test_reconcile"
        execution = ToolExecutionSpec(recovery=ToolRecoveryPolicy.RECONCILE)

        def reconcile(
            self,
            tool_input: EchoInput,
            context: ToolRunContext,
        ) -> ToolReconciliation:
            seen.append(context.idempotency_key)
            return ToolReconciliation(
                status="succeeded",
                output={"value": tool_input.value, "seen": {"thread_id": context.thread_id}},
            )

    result = ToolRuntime(ToolRegistry().register(ReconcileTool())).reconcile(
        tool_name="test_reconcile",
        raw_input={"value": "hello"},
        request=SimpleNamespace(session_id="session-1"),
        idempotency_key="stable-invocation-key",
    )

    assert result.status == "success"
    assert result.output == {"value": "hello", "seen": {"thread_id": "session-1"}}
    assert seen == ["stable-invocation-key"]


def test_runtime_rejects_unknown_or_encoded_arguments_instead_of_coercing_them():
    registry = ToolRegistry().register(EchoTool())
    unknown = ToolRuntime(registry).invoke(
        tool_name="test_echo",
        raw_input={"value": "hello", "legacy_value": "ignored-before"},
        request=None,
        idempotency_key="invocation-unknown",
    )
    encoded = ToolRuntime(registry).invoke(
        tool_name="test_echo",
        raw_input={"value": '{"not":"a string contract"}'},
        request=None,
        idempotency_key="invocation-encoded",
    )

    assert unknown.error_code == "TOOL_INPUT_CONTRACT_FAILED"
    assert encoded.status == "success"
    assert encoded.output == {
        "value": '{"not":"a string contract"}',
        "seen": {"thread_id": ""},
    }


def test_runtime_validation_and_execution_failures_are_safe(monkeypatch, caplog):
    class FailingTool(EchoTool):
        name = "test_failing"

        def run(self, _tool_input: EchoInput, _context: ToolRunContext) -> dict[str, Any]:
            raise RuntimeError("password=secret-sentinel")

    registry = ToolRegistry()
    registry.register(FailingTool())
    logger = logging.Logger("test.tool-runtime")
    logger.addHandler(caplog.handler)
    with monkeypatch.context() as patch:
        patch.setattr("engine.tools.runtime.runtime.logger", logger)
        invalid = ToolRuntime(registry).invoke(
            tool_name="test_failing", raw_input={}, request=None,
            idempotency_key="invocation-invalid",
        )
        failed = ToolRuntime(registry).invoke(
            tool_name="test_failing", raw_input={"value": "x"}, request=None,
            idempotency_key="invocation-failed",
        )
    assert invalid.status == "failed"
    assert "Input contract failed" in (invalid.error or "")
    assert failed.error == "Tool execution failed."
    assert "secret-sentinel" not in failed.model_dump_json()
    assert "secret-sentinel" not in caplog.text


def test_runtime_uses_registered_public_contract_for_domain_error() -> None:
    class DomainFailureTool(EchoTool):
        name = "test_domain_failure"

        def run(self, _tool_input: EchoInput, _context: ToolRunContext) -> dict[str, Any]:
            raise DBFoxError(
                "secret://driver-detail-must-not-cross-boundary",
                code="VALIDATION_FAILED",
            )

    result = ToolRuntime(ToolRegistry().register(DomainFailureTool())).invoke(
        tool_name="test_domain_failure",
        raw_input={"value": "x"},
        request=None,
        idempotency_key="invocation-domain-failure",
    )

    assert result.status == "failed"
    assert result.error_code == "VALIDATION_FAILED"
    assert result.error == "The request did not satisfy the required validation rules."
    assert result.output == {
        "status": "failed",
        "error_code": "VALIDATION_FAILED",
        "safe_message": "The request did not satisfy the required validation rules.",
    }
    assert "secret://" not in str(result.model_dump(mode="json"))


def test_runtime_collapses_unregistered_domain_error_to_internal_error() -> None:
    class UnregisteredFailureTool(EchoTool):
        name = "test_unregistered_domain_failure"

        def run(self, _tool_input: EchoInput, _context: ToolRunContext) -> dict[str, Any]:
            raise DBFoxError(
                "secret://unregistered-detail-must-not-cross-boundary",
                code="UNREGISTERED_DOMAIN_FAILURE",
            )

    result = ToolRuntime(ToolRegistry().register(UnregisteredFailureTool())).invoke(
        tool_name="test_unregistered_domain_failure",
        raw_input={"value": "x"},
        request=None,
        idempotency_key="invocation-unregistered-domain-failure",
    )

    assert result.status == "failed"
    assert result.error_code == "INTERNAL_ERROR"
    assert result.error == "The request could not be completed."
    assert result.output == {
        "status": "failed",
        "error_code": "INTERNAL_ERROR",
        "safe_message": "The request could not be completed.",
    }
    assert "secret://" not in str(result.model_dump(mode="json"))


def test_runtime_bounds_explicitly_public_tool_input_errors() -> None:
    class InvalidInputTool(EchoTool):
        name = "test_bounded_tool_input_error"

        def run(self, _tool_input: EchoInput, _context: ToolRunContext) -> dict[str, Any]:
            raise ToolInputError("x" * 10_000)

    result = ToolRuntime(ToolRegistry().register(InvalidInputTool())).invoke(
        tool_name="test_bounded_tool_input_error",
        raw_input={"value": "x"},
        request=None,
        idempotency_key="invocation-bounded-input-error",
    )

    assert result.status == "failed"
    assert result.error_code == "TOOL_INPUT_ERROR"
    assert result.error is not None
    assert len(result.error) == 1_025
    assert result.error.endswith("…")
    assert result.output["safe_message"] == result.error


def test_validation_error_raised_inside_tool_is_an_execution_failure():
    class InternalValidationTool(EchoTool):
        name = "test_internal_validation"

        def run(self, _tool_input: EchoInput, _context: ToolRunContext) -> dict[str, Any]:
            return EchoOutput.model_validate({}).model_dump()

    registry = ToolRegistry()
    registry.register(InternalValidationTool())
    result = ToolRuntime(registry).invoke(
        tool_name="test_internal_validation",
        raw_input={"value": "x"},
        request=None,
        idempotency_key="invocation-internal-validation",
    )

    assert result.error_code == "TOOL_EXECUTION_FAILED"
    assert result.error == "Tool execution failed."


def test_runtime_rejects_non_json_tool_output() -> None:
    class NonJsonOutputTool(EchoTool):
        name = "test_non_json_output"

        def run(self, _tool_input: EchoInput, _context: ToolRunContext) -> dict[str, Any]:
            return {"value": object()}

    result = ToolRuntime(ToolRegistry().register(NonJsonOutputTool())).invoke(
        tool_name="test_non_json_output",
        raw_input={"value": "x"},
        request=None,
        idempotency_key="invocation-non-json",
    )

    assert result.error_code == "TOOL_OUTPUT_CONTRACT_FAILED"
    assert result.error == "Output contract failed."


def test_product_registry_contains_only_kernel_tools_without_system_dlcs():
    from engine.runtime_composition import build_product_tool_registry

    names = {tool.name for tool in build_product_tool_registry().list_tools()}
    assert names == {
        "conversation_read",
        "conversation_search",
        "project_resource_search",
        "remote_job_cancel",
        "remote_job_status",
        "remote_job_submit",
        "request_clarification",
        "update_plan",
    }


def test_project_resource_search_pages_large_catalog_without_granting_authority(
    db_session,
):
    db_session.add(Project(id="resource-search-project", name="Resource search"))
    db_session.commit()
    db_session.add(
        AgentSession(
            id="resource-search-session",
            project_id="resource-search-project",
            title="Resource search",
        )
    )
    db_session.commit()

    def provider(_db, project_id):
        assert project_id == "resource-search-project"
        return tuple(
            ProjectResourceDescriptor(
                kind="verification.resource",
                id=f"resource-{index:03d}",
                version=index,
                name=f"Resource {index:03d}",
            )
            for index in range(75)
        )

    tool = ProjectResourceSearchTool((provider,))
    context = ToolRunContext.for_invocation(
        request=SimpleNamespace(session_id="resource-search-session"),
        idempotency_key="resource-search",
        metadata_session=db_session,
    )
    first = tool.run(ProjectResourceSearchInput(limit=50), context)
    second = tool.run(
        ProjectResourceSearchInput(limit=50, cursor=first.next_cursor),
        context,
    )

    assert first.returned_count == 50
    assert first.has_more is True
    assert first.next_cursor == "50"
    assert second.returned_count == 25
    assert second.has_more is False
    assert context.scope_refs == ()


def test_every_product_function_has_strict_input_and_output_contracts():
    from engine.runtime_composition import build_product_tool_registry

    for function in build_product_tool_registry().list_tools():
        assert function.input_model.model_config.get("extra") == "forbid"
        assert function.output_model.model_config.get("extra") == "forbid"


def test_large_observation_keeps_small_context_instead_of_dropping_all_facts():
    from engine.tools.runtime.observation import MAX_FACT_BYTES, safe_observation_facts

    facts = safe_observation_facts({
        "env": "dev",
        "dialect": "mysql",
        "database_map": {
            "tables": [
                {"name": f"table_{index}", "description": "x" * 1_000}
                for index in range(100)
            ],
        },
        "database_map_summary": {"tableCount": 100},
    })

    assert facts["truncated"] is True
    assert facts["env"] == "dev"
    assert facts["dialect"] == "mysql"
    assert facts["database_map_summary"] == {"tableCount": 100}
    assert facts["database_map"]["truncated"] is True
    assert len(json.dumps(facts, ensure_ascii=False).encode("utf-8")) <= MAX_FACT_BYTES


def test_tool_executor_retries_only_retry_safe_operations():
    class RetryTool(EchoTool):
        name = "test_retry"
        execution = ToolExecutionSpec(
            recovery=ToolRecoveryPolicy.RETRY_SAFE,
            retryable=True,
            max_retries=2,
        )

    attempts: list[int] = []

    def operation(_control):
        attempts.append(len(attempts) + 1)
        if len(attempts) < 3:
            return ToolResult(
                name="test_retry", status="failed", error="temporary",
                error_code="TOOL_EXECUTION_FAILED", latency_ms=1,
            )
        return ToolResult(name="test_retry", status="success", output={"ok": True}, latency_ms=1)

    result = ToolExecutor(max_workers=1).execute(
        tool=RetryTool(), scope_key="run-1", operation=operation,
    )

    assert result.status == "success"
    assert result.attempts == 3
    assert attempts == [1, 2, 3]


def test_tool_executor_retries_share_one_absolute_deadline():
    class RetryTool(EchoTool):
        name = "test_retry_deadline"
        execution = ToolExecutionSpec(
            timeout_seconds=1,
            recovery=ToolRecoveryPolicy.RETRY_SAFE,
            retryable=True,
            max_retries=5,
        )

    attempts = 0

    def operation(_control):
        nonlocal attempts
        attempts += 1
        time.sleep(0.02)
        return ToolResult(
            name="test_retry_deadline",
            status="failed",
            error="temporary",
            error_code="TOOL_EXECUTION_FAILED",
            latency_ms=20,
        )

    started = time.monotonic()
    result = ToolExecutor(max_workers=1, poll_interval_seconds=0.005).execute(
        tool=RetryTool(),
        scope_key="run-retry-deadline",
        operation=operation,
        deadline=started + 0.055,
    )

    assert result.error_code == "TOOL_TIMEOUT"
    assert result.attempts == attempts
    assert 1 <= attempts < 6
    assert time.monotonic() - started < 0.2


def test_tool_executor_timeout_signals_the_leaf_and_never_returns_late_success():
    cancelled = False

    def operation(control):
        while not control.is_cancelled():
            time.sleep(0.005)
        return ToolResult(name="test_echo", status="success", output={"late": True}, latency_ms=1)

    def cancel_action():
        nonlocal cancelled
        cancelled = True

    result = ToolExecutor(max_workers=1, poll_interval_seconds=0.005).execute(
        tool=EchoTool(), scope_key="run-timeout", operation=operation,
        cancel_action=cancel_action,
        deadline=time.monotonic() + 0.03,
    )

    assert result.status == "failed"
    assert result.error_code == "TOOL_TIMEOUT"
    assert cancelled is True


def test_tool_executor_replaces_capacity_after_non_cooperative_timeouts():
    release = threading.Event()
    executor = ToolExecutor(
        max_workers=1,
        max_abandoned_workers=8,
        poll_interval_seconds=0.005,
    )

    def stuck_operation(_control):
        release.wait()
        return ToolResult(
            name="test_echo",
            status="success",
            output={"late": True},
            latency_ms=1,
        )

    try:
        for index in range(5):
            result = executor.execute(
                tool=EchoTool(),
                scope_key=f"run-stuck-{index}",
                operation=stuck_operation,
                deadline=time.monotonic() + 0.02,
            )
            assert result.error_code == "TOOL_TIMEOUT"

        healthy = executor.execute(
            tool=EchoTool(),
            scope_key="run-healthy",
            operation=lambda _control: ToolResult(
                name="test_echo",
                status="success",
                output={"ok": True},
                latency_ms=1,
            ),
            deadline=time.monotonic() + 0.1,
        )
        assert healthy.status == "success"
    finally:
        release.set()
        executor.close(wait=True)


def test_tool_executor_fails_fast_at_the_abandoned_worker_limit():
    release = threading.Event()
    executor = ToolExecutor(
        max_workers=1,
        max_abandoned_workers=2,
        poll_interval_seconds=0.005,
    )

    def stuck_operation(_control):
        release.wait()
        return ToolResult(name="test_echo", status="success", output={}, latency_ms=1)

    try:
        for index in range(2):
            assert executor.execute(
                tool=EchoTool(),
                scope_key=f"run-limit-{index}",
                operation=stuck_operation,
                deadline=time.monotonic() + 0.02,
            ).error_code == "TOOL_TIMEOUT"

        saturated = executor.execute(
            tool=EchoTool(),
            scope_key="run-limit-saturated",
            operation=stuck_operation,
            deadline=time.monotonic() + 0.02,
        )
        assert saturated.error_code == "TOOL_EXECUTOR_SATURATED"
    finally:
        release.set()
        executor.close(wait=True)


def test_tool_executor_enforces_declared_output_bytes():
    class BoundedTool(EchoTool):
        name = "test_bounded"
        execution = ToolExecutionSpec(max_output_bytes=1_024)

    result = ToolExecutor(max_workers=1).execute(
        tool=BoundedTool(),
        scope_key="run-output",
        operation=lambda _control: ToolResult(
            name="test_bounded", status="success", output={"value": "x" * 2_000}, latency_ms=1,
        ),
    )

    assert result.status == "failed"
    assert result.error_code == "TOOL_OUTPUT_TOO_LARGE"
