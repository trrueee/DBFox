"""Independent executor deadlines and real process-death recovery; no GPU simulation."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import threading
import time
from uuid import uuid4

import pytest

from dbfox_dlc_api import ResourceScopeRef, ToolKey
from engine.runtime_composition import build_attempt_resource_resolver
from engine.tools.runtime import ToolRuntime
from engine.tools.runtime.executor import ToolExecutor
from verification.bench.capabilities.dbfox_shader.runtime import ShaderRuntime


def setup(runtime):
    project = str(uuid4())
    created = runtime.operation(project, 'documents.create', {'title': 'Original title', 'expected_generation': 0, 'request_id': str(uuid4())})
    owner = next(item.tool for item in runtime.snapshot.tools if item.owner_id == 'dbfox.shader' and item.tool.name == 'shader_modify')
    scope = ResourceScopeRef(kind='dbfox.shader.studio', id=project, version=1)
    resources = build_attempt_resource_resolver(snapshot=runtime.snapshot).resolve((scope,))
    identity = str(uuid4())
    common = dict(tool_name=runtime.registry.provider_name_for_key(ToolKey(owner_id='dbfox.shader', local_name='shader_modify')),
        raw_input={'document_id': created['document']['id'], 'expected_version': 1, 'operations': [{'kind': 'rename_document', 'title': 'Recovered exactly once'}]},
        request=None, invocation_id=identity, idempotency_key=identity, scope_refs=(scope,), resources=resources)
    return project, created['document']['id'], owner, common


def assert_recovery(runtime, project, document, common, phase):
    head = runtime.operation(project, 'documents.head', {'document_id': document})
    recovered = ToolRuntime(runtime.registry).reconcile(**common)
    if phase == 'before_commit':
        assert head['version'] == 1
        # Shader's accepted contract deliberately reports missing receipts as
        # unknown; absence is never used to authorize automatic replay.
        assert recovered.status == 'failed' and recovered.error_code == 'TOOL_OUTCOME_UNKNOWN'
    else:
        assert recovered.status == 'success' and recovered.output['document']['version'] == 2
        assert recovered.output['document']['title'] == 'Recovered exactly once'
        assert head['version'] == 2
    assert runtime.operation(project, 'documents.head', {'document_id': document}) == head


@pytest.mark.parametrize('phase', ['before_commit', 'after_commit'])
@pytest.mark.parametrize('termination', ['cancel', 'timeout'])
def test_actual_executor_boundary_reconciles_once(tmp_path, monkeypatch, phase, termination):
    with ShaderRuntime(tmp_path) as runtime:
        project, document, owner, common = setup(runtime)
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        method = 'save_receipt' if phase == 'before_commit' else 'mutate'
        original = getattr(owner.store, method)
        calls = 0

        def delayed(*args, **kwargs):
            nonlocal calls
            calls += 1
            result = original(*args, **kwargs)
            entered.set()
            assert release.wait(8), 'Independent boundary was not released'
            return result

        monkeypatch.setattr(owner.store, method, delayed)
        tool_runtime = ToolRuntime(runtime.registry)

        def operation(control):
            try:
                return tool_runtime.invoke(**common, cancellation_probe=control.is_cancelled, deadline=control.deadline)
            finally:
                finished.set()

        executor = ToolExecutor(max_workers=1, poll_interval_seconds=.01)
        try:
            result = executor.execute(tool=owner, scope_key=document, operation=operation,
                should_cancel=entered.is_set if termination == 'cancel' else None,
                deadline=time.monotonic() + (2 if termination == 'timeout' else 5))
            assert entered.is_set() and result.attempts == 1
            assert result.error_code == ('TOOL_TIMEOUT' if termination == 'timeout' else 'TOOL_CANCELLED')
            release.set()
            assert finished.wait(5)
            assert_recovery(runtime, project, document, common, phase)
            assert calls == 1, 'Reconciliation must never replay mutation logic'
        finally:
            release.set()
            executor.close()


@pytest.mark.parametrize('phase', ['before_commit', 'after_commit'])
def test_real_process_death_preserves_commit_truth_and_reconciles_without_replay(tmp_path, monkeypatch, phase):
    with ShaderRuntime(tmp_path) as runtime:
        project, document, owner, common = setup(runtime)
        result = subprocess.run([sys.executable, '-m', 'verification.testkit.shader_independent.crash_worker', str(tmp_path),
            project, document, common['invocation_id'], phase], cwd=Path(__file__).resolve().parents[3],
            capture_output=True, text=True, timeout=30)
        assert result.returncode == 37, (result.returncode, result.stdout, result.stderr)

        def forbidden(*_args, **_kwargs):
            pytest.fail('Recovery attempted to replay a committed or uncommitted mutation')

        monkeypatch.setattr(owner.store, 'mutate', forbidden)
        assert_recovery(runtime, project, document, common, phase)
