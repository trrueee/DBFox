"""P1 contracts for the explicit DBFox backend composition root."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.agent.completion import CompletionGate
from engine.agent.loop import RunLoop
from engine.runtime_composition import (
    build_attempt_resource_resolver,
    build_default_completion_policy,
    build_product_tool_registry,
    default_context_contributors,
)
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.workspace.read_service import WorkspaceReadService


def test_product_registry_is_frozen_and_keeps_owner_and_backend_contracts() -> None:
    registry = build_product_tool_registry()

    assert registry.frozen is True
    assert registry.owner_of("remote_job_submit") == "dbfox.remote_job"
    assert {
        registry.require(name).execution.backend
        for name in (
            "remote_job_submit",
            "remote_job_status",
            "remote_job_cancel",
        )
    } == {"in_process"}


def test_default_attempt_resolver_preserves_database_and_workspace_contracts(
    tmp_path: Path,
) -> None:
    resolver = build_attempt_resource_resolver()
    workspace = resolver.resolve(
        (
            ResourceScopeRef(
                kind="workspace",
                id="workspace-1",
                location=str(tmp_path),
            ),
        )
    )["workspace"]

    assert isinstance(workspace, WorkspaceReadService)
    assert workspace.root == tmp_path.resolve()
    with pytest.raises(RuntimeError, match="frozen"):
        resolver.register("test", lambda _ref: None)
    with pytest.raises(KeyError, match="No resolver"):
        resolver.resolve((ResourceScopeRef(kind="unknown", id="unknown"),))


def test_run_loop_accepts_explicit_product_composition() -> None:
    registry = build_product_tool_registry()
    contributors = default_context_contributors()
    completion = CompletionGate(build_default_completion_policy())
    loop = RunLoop(
        session_factory=lambda: None,  # type: ignore[arg-type]
        registry=registry,
        context_contributors=contributors,
        completion=completion,
    )
    try:
        assert loop.registry is registry
        assert loop.context_contributors is contributors
        assert loop.completion is completion
    finally:
        loop.tool_executor.close()


def test_kernel_modules_do_not_own_concrete_dlc_composition() -> None:
    root = Path(__file__).parents[1]
    loop_source = (root / "agent" / "loop.py").read_text(encoding="utf-8")
    context_source = (root / "agent" / "context.py").read_text(encoding="utf-8")
    completion_source = (root / "agent" / "completion.py").read_text(encoding="utf-8")

    assert "engine.tools.builtin" not in loop_source
    assert "WorkspaceContextContributor" not in context_source
    assert "completion_data" not in completion_source
    assert "completion_defaults" not in completion_source


def test_worker_and_engine_startup_use_product_composition_root() -> None:
    root = Path(__file__).parents[1]
    worker_source = (root / "tools" / "worker.py").read_text(encoding="utf-8")
    main_source = (root / "main.py").read_text(encoding="utf-8")

    assert "build_product_tool_registry()" in worker_source
    assert "build_attempt_resource_resolver()" in worker_source
    assert "register_" not in worker_source
    assert "build_product_run_loop(session_factory=SessionLocal)" in main_source
