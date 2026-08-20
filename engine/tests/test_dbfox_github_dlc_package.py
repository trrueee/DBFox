"""Conformance coverage for the external dbfox.github source tree and package."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import sys
import zipfile

import pytest

from engine.agent.artifact import artifact_payload_contracts
from engine.dlc import ContributionCompiler, DlcPackageService
from engine.dlc.api import DlcOperationContext, ResourceScopeRef
from engine.dlc.loader import derive_dlc_namespace
from scripts.build_dbfox_github_dlc_fixture import SOURCE_ROOT, build_dbfox_github_dlc_fixture


@pytest.fixture
def github_artifact_contract_available() -> Iterator[None]:
    original_contracts = dict(artifact_payload_contracts._contracts)
    original_frozen = artifact_payload_contracts._frozen
    artifact_payload_contracts._contracts.pop(("dbfox.github.file_snapshot", 1), None)
    artifact_payload_contracts._frozen = False
    try:
        yield
    finally:
        artifact_payload_contracts._contracts = original_contracts
        artifact_payload_contracts._frozen = original_frozen


def test_github_dlc_source_uses_only_public_extension_boundaries() -> None:
    backend_sources = sorted((SOURCE_ROOT / "backend").glob("*.py"))
    assert backend_sources
    for source in backend_sources:
        text = source.read_text(encoding="utf-8")
        assert "from engine" not in text
        assert "import engine" not in text
    frontend = (SOURCE_ROOT / "frontend" / "index.js").read_text(encoding="utf-8")
    assert "../../" not in frontend
    assert "fetch(" not in frontend
    assert "extensionHost.operations.invoke" in frontend
    assert "extensionHost.dockViews.open" in frontend


def test_signed_github_dlc_package_activates_complete_contribution_set(
    tmp_path: Path,
    github_artifact_contract_available: None,
) -> None:
    built = build_dbfox_github_dlc_fixture(tmp_path / "archives")
    with zipfile.ZipFile(built.archive) as archive:
        names = set(archive.namelist())
    assert "backend/entry.py" in names
    assert "frontend/index.js" in names
    assert "frontend/index.css" in names
    assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)

    service = DlcPackageService(tmp_path / "runtime" / "dlcs")
    inspection = service.inspect_from_file(built.archive)
    assert inspection.package_digest == built.package_digest
    assert inspection.publisher_key_id == built.publisher_fingerprint
    service.trust_publisher_from_file(
        built.archive,
        expected_package_digest=built.package_digest,
        expected_publisher_key_id=built.publisher_fingerprint,
    )
    service.install_from_file(built.archive)
    service.set_desired_enabled("dbfox.github", True)

    snapshot = ContributionCompiler(service.storage_root).compile(
        built_in_tools=[],
        built_in_resource_providers=[],
        built_in_resource_resolvers=[],
        built_in_context_contributors=[],
    )
    assert snapshot.activation_failures == ()
    assert [(item.dlc_id, item.package_digest) for item in snapshot.active_dlcs] == [
        ("dbfox.github", built.package_digest)
    ]
    assert {item.tool.name for item in snapshot.tools} == {
        "github_repo_overview",
        "github_list_files",
        "github_read_file",
    }
    assert all(item.owner_id == "dbfox.github" for item in snapshot.tools)
    assert [item.kind for item in snapshot.resource_resolvers] == ["github.repository"]
    assert [item.owner_id for item in snapshot.artifact_contracts] == ["dbfox.github"]
    assert {item.spec.name for item in snapshot.operations} == {
        "bindings.list",
        "bindings.create",
        "bindings.delete",
        "bindings.refresh",
        "files.list",
        "files.read",
    }

    operation = snapshot.get_operation("dbfox.github", "bindings.list")
    assert operation is not None
    output = operation.spec.handler(
        operation.spec.input_model(),
        DlcOperationContext(
            dlc_id="dbfox.github",
            operation_name="bindings.list",
            project_id="project-a",
        ),
    )
    assert operation.spec.output_model.model_validate(output).model_dump() == {
        "bindings": []
    }
    assert (service.storage_root / "data" / "dbfox.github" / "state.sqlite3").is_file()

    namespace = derive_dlc_namespace("dbfox.github", built.package_digest)
    service_module = sys.modules[f"{namespace}.service"]
    store_module = sys.modules[f"{namespace}.store"]
    assert service_module.normalize_github_repository("https://github.com/astral-sh/uv") == (
        "astral-sh",
        "uv",
    )
    for unsafe_repository in (
        "http://github.com/acme/repo",
        "https://github.com:8443/acme/repo",
        "https://example.com/acme/repo",
        "https://github.com/acme/repo?token=secret",
    ):
        with pytest.raises(service_module.GithubInvalidInputError):
            service_module.normalize_github_repository(unsafe_repository)
    with pytest.raises(service_module.GithubInvalidInputError):
        service_module.normalize_repository_relative_path("../secret")

    store = store_module.GithubBindingStore(
        service.storage_root / "data" / "dbfox.github"
    )
    binding = store.create_binding(
        project_id="project-a",
        owner="astral-sh",
        repository="uv",
        ref_name="main",
        resolved_revision="a" * 40,
        default_branch="main",
        description="fixture",
    )
    resources = snapshot.resource_providers[0](None, "project-a")
    assert [(item.kind, item.id, item.version) for item in resources] == [
        ("github.repository", binding.id, "a" * 40)
    ]
    resolved = snapshot.resource_resolvers[0].resolver(
        ResourceScopeRef(
            kind="github.repository",
            id=binding.id,
            version="a" * 40,
        )
    )
    assert resolved.binding_id == binding.id
    with pytest.raises(ValueError):
        snapshot.resource_resolvers[0].resolver(
            ResourceScopeRef(
                kind="github.repository",
                id=binding.id,
                version="b" * 40,
            )
        )
