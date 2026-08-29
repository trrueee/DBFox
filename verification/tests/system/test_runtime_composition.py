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
from engine.dlc import BuiltinContributionSet, ContributionCompiler
from engine.tools.runtime import ToolRegistry
from engine.tools.runtime.attempt import ResourceScopeRef


def test_builtin_seed_identity_participates_in_snapshot_id(tmp_path: Path) -> None:
    compiler = ContributionCompiler(tmp_path / "dlcs")

    empty = compiler.compile(built_ins=BuiltinContributionSet())
    legacy_data = compiler.compile(
        built_ins=BuiltinContributionSet(identifiers=("legacy.dbfox.data",))
    )
    reordered_a = compiler.compile(
        built_ins=BuiltinContributionSet(identifiers=("dbfox.core", "dbfox.remote_job"))
    )
    reordered_b = compiler.compile(
        built_ins=BuiltinContributionSet(identifiers=("dbfox.remote_job", "dbfox.core"))
    )

    assert empty.snapshot_id != legacy_data.snapshot_id
    assert reordered_a.snapshot_id == reordered_b.snapshot_id
    assert empty.tools == ()


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


def test_default_attempt_resolver_does_not_reintroduce_workspace_domain() -> None:
    resolver = build_attempt_resource_resolver()
    workspace_ref = ResourceScopeRef(
        kind="dbfox.workspace.root",
        id="workspace-1",
        version="workspace-digest",
    )
    with pytest.raises(KeyError, match="No resolver"):
        resolver.resolve((workspace_ref,))

    with pytest.raises(RuntimeError, match="frozen"):
        resolver.register("synthetic.test", lambda _ref: None)
    with pytest.raises(KeyError, match="No resolver"):
        resolver.resolve((ResourceScopeRef(kind="synthetic.unknown", id="unknown"),))


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


def test_run_loop_preserves_explicit_empty_context_contributors() -> None:
    loop = RunLoop(
        session_factory=lambda: None,  # type: ignore[arg-type]
        registry=build_product_tool_registry(),
        context_contributors=(),
        completion=CompletionGate(build_default_completion_policy()),
    )
    try:
        assert loop.context_contributors == ()
    finally:
        loop.tool_executor.close()


def test_run_loop_preserves_explicit_empty_frozen_registry() -> None:
    registry = ToolRegistry().freeze()
    loop = RunLoop(
        session_factory=lambda: None,  # type: ignore[arg-type]
        registry=registry,
        context_contributors=default_context_contributors(),
        completion=CompletionGate(build_default_completion_policy()),
    )
    try:
        assert loop.registry is registry
        assert loop.context_contributors == default_context_contributors()
    finally:
        loop.tool_executor.close()


def test_run_loop_preserves_explicit_completion_gate() -> None:
    completion = CompletionGate(build_default_completion_policy())
    loop = RunLoop(
        session_factory=lambda: None,  # type: ignore[arg-type]
        registry=build_product_tool_registry(),
        context_contributors=default_context_contributors(),
        completion=completion,
    )
    try:
        assert loop.completion is completion
    finally:
        loop.tool_executor.close()


def test_run_loop_requires_explicit_product_composition() -> None:
    with pytest.raises(TypeError, match="registry"):
        RunLoop(session_factory=lambda: None)  # type: ignore[call-arg,arg-type]


def test_kernel_modules_do_not_own_concrete_dlc_composition() -> None:
    root = Path(__file__).resolve().parents[3] / "engine"
    loop_source = (root / "agent" / "loop.py").read_text(encoding="utf-8")
    context_source = (root / "agent" / "context.py").read_text(encoding="utf-8")
    completion_source = (root / "agent" / "completion.py").read_text(encoding="utf-8")

    assert "engine.tools.builtin" not in loop_source
    assert "engine.runtime_composition" not in loop_source
    assert "WorkspaceContextContributor" not in context_source
    assert "completion_data" not in completion_source
    assert "completion_defaults" not in completion_source


def test_worker_and_engine_startup_use_product_composition_root() -> None:
    root = Path(__file__).resolve().parents[3] / "engine"
    worker_source = (root / "tools" / "worker.py").read_text(encoding="utf-8")
    main_source = (root / "main.py").read_text(encoding="utf-8")

    assert "build_product_tool_registry()" in worker_source
    assert "build_attempt_resource_resolver()" in worker_source
    assert "register_" not in worker_source
    assert "build_product_run_loop(session_factory=SessionLocal)" in main_source
