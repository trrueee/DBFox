"""Conformance coverage for the external dbfox.workspace System DLC."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from engine.agent.artifact import artifact_payload_contracts
from engine.agent.context_fragment import (
    ContextArtifactObservation,
    ContextContributionInput,
)
from engine.dlc import BuiltinContributionSet, ContributionCompiler, DlcPackageService
from engine.dlc.api import DlcOperationContext, ResourceScopeRef
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
) -> None:
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
    assert {item.tool.name for item in snapshot.tools} == {"file_search", "file_read"}
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

    service.set_desired_enabled("dbfox.workspace", False)
    absent = ContributionCompiler(service.storage_root).compile(
        built_ins=BuiltinContributionSet()
    )
    assert absent.active_dlcs == ()
    assert absent.resource_resolvers == ()
    assert (service.storage_root / "data" / "dbfox.workspace" / "state.sqlite3").is_file()
