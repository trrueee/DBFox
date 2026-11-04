"""Conformance coverage for the external dbfox.workspace System DLC."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import sys
import time

import pytest

from engine.agent.artifact import artifact_payload_contracts
from engine.agent.context_fragment import (
    ContextArtifactObservation,
    ContextContributionInput,
)
from engine.dlc import BuiltinContributionSet, ContributionCompiler, DlcPackageService
from engine.dlc.api import DlcOperationContext, ResourceScopeRef
from engine.runtime_composition import build_product_tool_registry
from engine.tools.materialization import current_tool_contract_hash
from engine.tools.runtime.attempt import ToolAttemptRequest, ToolInvocationContext
from engine.tools.runtime.attempt_runner import IsolatedProcessAttemptRunner
from scripts.build_dbfox_workspace_dlc_fixture import (
    SOURCE_ROOT,
    build_dbfox_workspace_dlc_fixture,
)


@pytest.fixture
def workspace_contracts_available() -> Iterator[None]:
    original_contracts = dict(artifact_payload_contracts._contracts)
    original_frozen = artifact_payload_contracts._frozen
    for artifact_type in (
        "dbfox.workspace.file_snapshot",
        "dbfox.workspace.code_patch",
    ):
        artifact_payload_contracts._contracts.pop((artifact_type, 1), None)
    artifact_payload_contracts._frozen = False
    try:
        yield
    finally:
        artifact_payload_contracts._contracts = original_contracts
        artifact_payload_contracts._frozen = original_frozen


def test_workspace_dlc_source_uses_only_public_extension_boundaries() -> None:
    for source in sorted((SOURCE_ROOT / "backend").glob("*.py")):
        value = source.read_text(encoding="utf-8")
        assert "from engine" not in value
        assert "import engine" not in value
    frontend = (SOURCE_ROOT / "frontend" / "index.js").read_text(encoding="utf-8")
    assert "../../" not in frontend
    assert "fetch(" not in frontend
    assert "host.nativeDialogs.pickFolder" in frontend
    assert "host.dockViews.open" in frontend
    assert "requestedResources" not in frontend


def test_workspace_dlc_owns_binding_resource_tools_and_file_operations(
    tmp_path: Path,
    workspace_contracts_available: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DBFOX_RUNTIME_DIR", str(tmp_path / "runtime"))
    built = build_dbfox_workspace_dlc_fixture(tmp_path / "archives")
    service = DlcPackageService(tmp_path / "runtime" / "dlcs")
    service.trust_publisher_from_file(
        built.archive,
        expected_package_digest=built.package_digest,
        expected_publisher_key_id=built.publisher_fingerprint,
    )
    service.install_from_file(built.archive)
    service.set_desired_enabled("dbfox.workspace", True)
    snapshot = ContributionCompiler(service.storage_root).compile(
        built_ins=BuiltinContributionSet()
    )
    assert snapshot.activation_failures == ()
    assert {item.tool.name for item in snapshot.tools} == {
        "command_run",
        "file_delete",
        "file_edit",
        "file_grep",
        "file_move",
        "file_read",
        "file_search",
        "file_write",
    }
    assert [item.kind for item in snapshot.resource_resolvers] == ["dbfox.workspace.root"]
    assert {item.artifact_type for item in snapshot.artifact_contracts} == {
        "dbfox.workspace.file_snapshot",
        "dbfox.workspace.code_patch",
    }
    assert {item.spec.name for item in snapshot.operations} == {
        "binding.get",
        "binding.create",
        "binding.delete",
        "files.list",
        "files.read",
        "files.write",
        "files.edit",
        "files.delete",
        "files.move",
        "files.grep",
    }

    workspace = tmp_path / "project-files"
    workspace.mkdir()
    (workspace / "notes.txt").write_text("hello workspace", encoding="utf-8")
    create = snapshot.get_operation("dbfox.workspace", "binding.create")
    assert create is not None
    context = DlcOperationContext(
        dlc_id="dbfox.workspace",
        operation_name="binding.create",
        project_id="project-a",
    )
    binding = create.spec.output_model.model_validate(create.spec.handler(
        create.spec.input_model(root_path=str(workspace)),
        context,
    ))
    resources = snapshot.resource_providers[0](None, "project-a")
    assert [(item.kind, item.id, item.version) for item in resources] == [
        ("dbfox.workspace.root", "project-a", binding.root_digest)
    ]
    resolved = snapshot.resource_resolvers[0].resolver(ResourceScopeRef(
        kind="dbfox.workspace.root",
        id="project-a",
        version=binding.root_digest,
    ))
    assert resolved.read_text_file("notes.txt").content == "hello workspace"

    listing = snapshot.get_operation("dbfox.workspace", "files.list")
    assert listing is not None
    output = listing.spec.output_model.model_validate(listing.spec.handler(
        listing.spec.input_model(path=""),
        DlcOperationContext(
            dlc_id="dbfox.workspace",
            operation_name="files.list",
            project_id="project-a",
        ),
    ))
    assert [(entry.name, entry.is_dir) for entry in output.entries] == [
        ("notes.txt", False)
    ]

    scope = ResourceScopeRef(
        kind="dbfox.workspace.root",
        id="project-a",
        version=binding.root_digest,
    )

    with pytest.raises(ValueError, match="must not contain"):
        resolved.read_text_file("../outside.txt")
    (workspace / "binary.bin").write_bytes(bytes((0, 1, 2)))
    with pytest.raises(ValueError, match="binary"):
        resolved.read_text_file("binary.bin")
    (workspace / "oversized.txt").write_bytes(b"x" * (1024 * 1024 + 1))
    with pytest.raises(ValueError, match="1 MiB"):
        resolved.read_text_file("oversized.txt")

    snapshot_file = resolved.read_text_file("notes.txt")
    observation = ContextArtifactObservation(
        observation_id="observation-a",
        artifact_id="artifact-a",
        artifact_type="dbfox.workspace.file_snapshot",
        schema_version=1,
        resource_refs=(scope,),
        payload={
            "relativePath": "notes.txt",
            "sizeBytes": snapshot_file.size_bytes,
            "sha256": snapshot_file.sha256,
            "truncated": False,
            "workspaceId": scope.id,
            "workspaceVersion": scope.version or "",
        },
    )
    contribution_input = ContextContributionInput(
        session_id="session-a",
        run_id="run-a",
        current_request="summarize",
        resource_refs=(scope,),
        recent_artifacts=(observation,),
    )
    contributor = snapshot.context_contributors[0](None)
    assert len(contributor.build(contribution_input)) == 1

    tools = {item.tool.name: item.tool for item in snapshot.tools}
    for name in ("file_write", "file_edit", "file_delete", "file_move", "command_run"):
        assert tools[name].execution.backend == "isolated_process"
        assert tools[name].policy.requires_approval is True
    read_projection = tools["file_read"].project_observation(
        status="success",
        output={
            "path": "notes.txt",
            "content": "hello workspace",
            "content_truncated": False,
            "size_bytes": 15,
            "sha256": "a" * 64,
        },
        artifacts=[],
    )
    assert "content" not in read_projection.facts
    assert read_projection.provider_payload["content"] == "hello workspace"
    search_projection = tools["file_search"].project_observation(
        status="success",
        output={
            "query": "notes",
            "path_prefix": "",
            "matches": [{"name": "notes.txt", "path": "notes.txt", "is_dir": False}],
            "returned_count": 1,
            "truncated": False,
        },
        artifacts=[],
    )
    assert "matches" not in search_projection.facts
    assert search_projection.provider_payload["matches"][0]["name"] == "notes.txt"

    (workspace / "notes.txt").write_text("changed", encoding="utf-8")
    assert contributor.build(contribution_input) == ()

    created = resolved.write_text_file("drafts/chapter.md", "第一段")
    assert created.content == "第一段"
    edited = resolved.edit_text_file(
        "drafts/chapter.md",
        old_string="第一段",
        new_string="第一段修改",
        expected_sha256=created.sha256,
    )
    assert edited.content == "第一段修改"
    with pytest.raises(ValueError, match="changed"):
        resolved.edit_text_file(
            "drafts/chapter.md",
            old_string="第一段修改",
            new_string="过期编辑",
            expected_sha256=created.sha256,
        )
    grep_result = resolved.grep_text_files("修改", path_prefix="drafts")
    assert [(match.relative_path, match.line_number) for match in grep_result.matches] == [
        ("drafts/chapter.md", 1)
    ]
    resolved.move_path("drafts/chapter.md", "drafts/renamed.md")
    resolved.delete_path("drafts/renamed.md")
    command = resolved.run_command(
        (sys.executable, "-c", "print('bounded command')"),
        timeout_seconds=10,
    )
    assert command.exit_code == 0
    assert command.timed_out is False
    assert "bounded command" in command.output

    service_module = sys.modules[type(resolved).__module__]
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "must-not-leak")
    monkeypatch.setenv("DBFOX_ENGINE_TOKEN", "must-not-leak")
    command_environment = service_module._command_environment()
    assert "AWS_ACCESS_KEY_ID" not in command_environment
    assert "DBFOX_ENGINE_TOKEN" not in command_environment
    if "PATH" in command_environment:
        assert command_environment["PATH"]
    monkeypatch.setattr(service_module, "MAX_COMMAND_STREAM_BYTES", 4_096)
    limited = resolved.run_command(
        (sys.executable, "-c", "print('x' * 10000)"),
        timeout_seconds=10,
    )
    assert limited.output_limit_exceeded is True
    assert limited.truncated is True
    assert len(limited.output.encode("utf-8")) <= service_module.MAX_COMMAND_OUTPUT_BYTES

    bounded_dir = workspace / "bounded-dir"
    bounded_dir.mkdir()
    for index in range(8):
        (bounded_dir / f"{index}.txt").write_text(str(index), encoding="utf-8")
    monkeypatch.setattr(service_module, "MAX_WORKSPACE_DIR_ENTRIES", 3)
    monkeypatch.setattr(service_module, "MAX_WORKSPACE_DIR_SCAN_ENTRIES", 5)
    directory = resolved.list_directory("bounded-dir")
    assert len(directory.entries) == 3
    assert directory.truncated is True

    monkeypatch.setattr(service_module, "MAX_GREP_FILES", 2)
    grep_limited = resolved.grep_text_files("not-present", path_prefix="bounded-dir")
    assert grep_limited.scanned_files == 2
    assert grep_limited.truncated is True

    registry = build_product_tool_registry(snapshot)
    write_name = next(
        item.provider_name for item in snapshot.tools if item.tool.name == "file_write"
    )
    write_tool = registry.require(write_name)

    class _Control:
        deadline = time.monotonic() + 30

        @staticmethod
        def is_cancelled() -> bool:
            return False

    isolated_result = IsolatedProcessAttemptRunner().run(
        request=ToolAttemptRequest(
            mode="execute",
            tool_name=write_name,
            frozen_tool_declared_version=write_tool.version,
            frozen_tool_contract_hash=current_tool_contract_hash(write_tool),
            invocation=ToolInvocationContext(
                session_id="session-isolated",
                run_id="run-isolated",
                turn_id="turn-isolated",
                invocation_id="invocation-isolated",
                idempotency_key="idempotency-isolated",
                scope_refs=(scope,),
            ),
            authorized_input={
                "path": "isolated.txt",
                "content": "written through worker",
                "expected_sha256": None,
            },
            attempt_timeout_ms=20_000,
            implementation=registry.implementation_identity_of(write_name),
        ),
        control=_Control(),
    )
    assert isolated_result.status == "success"
    assert (workspace / "isolated.txt").read_text(encoding="utf-8") == "written through worker"

    service.set_desired_enabled("dbfox.workspace", False)
    absent = ContributionCompiler(service.storage_root).compile(
        built_ins=BuiltinContributionSet()
    )
    assert absent.active_dlcs == ()
    assert absent.resource_resolvers == ()
    assert (service.storage_root / "data" / "dbfox.workspace" / "state.sqlite3").is_file()
