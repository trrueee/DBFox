"""Conformance coverage for the external dbfox.github source tree and package."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
import sys
import zipfile

import pytest

from engine.agent.artifact import artifact_payload_contracts
from engine.agent.repositories.session import SessionRepository
from engine.agent.session import DeliveryMode
from engine.dlc import BuiltinContributionSet, ContributionCompiler, DlcPackageService
from engine.dlc.api import DlcOperationContext, ResourceScopeRef
from engine.dlc.loader import derive_dlc_namespace
from engine.models import AgentSession, AgentToolInvocation
from engine.tools.materialization import current_tool_contract_hash
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
        built_ins=BuiltinContributionSet()
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
    assert [item.kind for item in snapshot.resource_resolvers] == ["dbfox.github.repository"]
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
        ("dbfox.github.repository", binding.id, "a" * 40)
    ]
    resolved = snapshot.resource_resolvers[0].resolver(
        ResourceScopeRef(
            kind="dbfox.github.repository",
            id=binding.id,
            version="a" * 40,
        )
    )
    assert resolved.binding_id == binding.id
    with pytest.raises(ValueError):
        snapshot.resource_resolvers[0].resolver(
            ResourceScopeRef(
                kind="dbfox.github.repository",
                id=binding.id,
                version="b" * 40,
            )
        )


def _record_github_tool_history(db_session, snapshot, package_digest: str) -> str:
    now = datetime.now(UTC)
    session_id = "r5-github-history"
    db_session.add(
        AgentSession(
            id=session_id,
            title="R5 GitHub history",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()

    repository = SessionRepository(db_session)
    admission = repository.admit(
        session_id=session_id,
        resource_refs=(),
        content="Inspect a GitHub repository",
        idempotency_key="r5-github-history-input",
        llm_credential_id="r5-fixture-credential",
        api_base="https://api.openai.com/v1",
        model_name="fixture",
        request_payload={"content": "Inspect a GitHub repository"},
        delivery_mode=DeliveryMode.QUEUE,
    )
    lease = repository.claim(session_id=session_id, owner="r5-conformance")
    assert lease is not None
    assert repository.promote_next_input(lease=lease) == admission.run_id
    turn = repository.start_turn(
        lease=lease,
        run_id=admission.run_id,
        agent_definition_version="r5@1",
        prompt_version="r5@1",
        prompt_hash="r5-prompt",
        context_snapshot={},
        context_hash="r5-context",
        tool_materialization={"tools": []},
        tool_materialization_hash="r5-tools",
        provider="fixture",
        model_name="fixture",
    )
    contribution = next(
        item for item in snapshot.tools if item.tool.name == "github_repo_overview"
    )
    invocation_id = "r5-github-invocation"
    db_session.add(
        AgentToolInvocation(
            id=invocation_id,
            session_id=session_id,
            run_id=admission.run_id,
            turn_id=str(turn.id),
            provider_call_id="r5-github-provider-call",
            tool_name=contribution.provider_name or contribution.tool.name,
            declared_version=contribution.tool.version,
            contract_hash=current_tool_contract_hash(contribution.tool),
            owner_id=contribution.owner_id,
            package_digest=package_digest,
            input_json="{}",
            input_hash="r5-github-input-hash",
            idempotency_key="r5-github-tool-idempotency",
            status="succeeded",
            policy_json='{"status":"allowed","risk_level":"safe"}',
            presentation_json=json.dumps(
                contribution.tool.presentation.model_dump(mode="json"),
                sort_keys=True,
            ),
            recovery_policy=contribution.tool.execution.recovery.value,
            attempt_count=1,
            created_at=now,
            started_at=now,
            completed_at=now,
        )
    )
    db_session.commit()
    return invocation_id


def test_github_dlc_full_lifecycle_preserves_owned_data_and_attempt_identity(
    tmp_path: Path,
    db_session,
    github_artifact_contract_available: None,
) -> None:
    storage_root = tmp_path / "runtime" / "dlcs"
    compiler = ContributionCompiler(storage_root)

    absent = compiler.compile()
    assert not any(item.owner_id == "dbfox.github" for item in absent.tools)
    assert not any(item.kind == "dbfox.github.repository" for item in absent.resource_resolvers)
    assert absent.get_operation("dbfox.github", "bindings.list") is None
    assert not any(item.dlc_id == "dbfox.github" for item in absent.active_dlcs)

    built = build_dbfox_github_dlc_fixture(tmp_path / "archives")
    service = DlcPackageService(storage_root)
    inspection = service.inspect_from_file(built.archive)
    service.trust_publisher_from_file(
        built.archive,
        expected_package_digest=inspection.package_digest,
        expected_publisher_key_id=str(inspection.publisher_key_id),
    )
    installed = service.install_from_file(built.archive)
    assert service.registry.get_installed_dlc("dbfox.github").desired_enabled is False  # type: ignore[union-attr]

    installed_disabled = compiler.compile()
    assert installed_disabled.active_dlcs == ()
    assert not any(item.owner_id == "dbfox.github" for item in installed_disabled.tools)
    state_path = storage_root / "data" / "dbfox.github" / "state.sqlite3"
    assert not state_path.exists()

    service.set_desired_enabled("dbfox.github", True)
    assert installed_disabled.get_operation("dbfox.github", "bindings.list") is None
    assert not state_path.exists()

    active = compiler.compile()
    assert [(item.dlc_id, item.package_digest) for item in active.active_dlcs] == [
        ("dbfox.github", installed.package_digest)
    ]
    assert {item.tool.name for item in active.tools if item.owner_id == "dbfox.github"} == {
        "github_repo_overview",
        "github_list_files",
        "github_read_file",
    }
    operation = active.get_operation("dbfox.github", "bindings.list")
    assert operation is not None
    output = operation.spec.handler(
        operation.spec.input_model(),
        DlcOperationContext(
            dlc_id="dbfox.github",
            operation_name="bindings.list",
            project_id="r5-project",
        ),
    )
    assert operation.spec.output_model.model_validate(output).model_dump() == {
        "bindings": []
    }
    assert state_path.is_file()
    invocation_id = _record_github_tool_history(
        db_session,
        active,
        installed.package_digest,
    )

    service.set_desired_enabled("dbfox.github", False)
    assert active.get_operation("dbfox.github", "bindings.list") is operation

    inactive = compiler.compile()
    assert not any(item.dlc_id == "dbfox.github" for item in inactive.active_dlcs)
    assert not any(item.owner_id == "dbfox.github" for item in inactive.tools)
    assert inactive.get_operation("dbfox.github", "bindings.list") is None

    uninstall = service.uninstall(
        "dbfox.github",
        active_package_digests={
            item.package_digest for item in inactive.active_dlcs
        },
    )
    assert uninstall.executable_bytes_removed is True
    assert not service.store.get_package_dir(installed.package_digest).exists()
    assert state_path.is_file()
    with sqlite3.connect(state_path) as state:
        assert state.execute("SELECT COUNT(*) FROM repository_bindings").fetchone()[0] == 0

    history = db_session.get(AgentToolInvocation, invocation_id)
    assert history is not None
    assert history.owner_id == "dbfox.github"
    assert history.package_digest == installed.package_digest
