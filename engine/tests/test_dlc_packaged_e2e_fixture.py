"""Fast diagnostics for the signed fixture used by packaged release contracts."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from engine.dlc import ContributionCompiler, DlcError, DlcErrorCode, DlcPackageService
from engine.dlc.api import DlcOperationContext
from scripts.build_dlc_e2e_fixture import build_dlc_e2e_fixtures


@pytest.fixture
def mutable_artifact_contracts() -> Iterator[None]:
    from engine.agent.artifact import artifact_payload_contracts

    original_contracts = dict(artifact_payload_contracts._contracts)
    original_frozen = artifact_payload_contracts._frozen
    artifact_payload_contracts._frozen = False
    yield
    artifact_payload_contracts._contracts = original_contracts
    artifact_payload_contracts._frozen = original_frozen


def test_acme_echo_fixture_authenticates_and_activates_only_after_enable(
    tmp_path: Path,
    mutable_artifact_contracts: None,
) -> None:
    built = build_dlc_e2e_fixtures(tmp_path / "archives")
    service = DlcPackageService(tmp_path / "runtime" / "dlcs")
    marker_path = service.storage_root / "data" / "acme.echo" / "activation-marker.txt"

    with pytest.raises(DlcError) as tampered:
        service.inspect_from_file(built.tampered_archive)
    assert tampered.value.code == DlcErrorCode.HASH_MISMATCH
    assert service.registry.list_installed_dlcs() == []

    inspection = service.inspect_from_file(built.valid_archive)
    assert inspection.package_digest == built.package_digest
    assert inspection.publisher_key_id == built.publisher_fingerprint
    assert not marker_path.exists()

    service.trust_publisher_from_file(
        built.valid_archive,
        expected_package_digest=built.package_digest,
        expected_publisher_key_id=built.publisher_fingerprint,
    )
    service.install_from_file(built.valid_archive)
    assert not marker_path.exists()

    service.set_desired_enabled("acme.echo", True)
    assert not marker_path.exists()
    snapshot = ContributionCompiler(service.storage_root).compile(
        built_in_tools=[],
        built_in_resource_providers=[],
        built_in_resource_resolvers=[],
        built_in_context_contributors=[],
    )

    assert snapshot.activation_failures == ()
    assert len(snapshot.active_dlcs) == 1
    assert snapshot.active_dlcs[0].package_digest == built.package_digest
    assert marker_path.read_text(encoding="utf-8") == built.package_digest
    assert [item.artifact_type for item in snapshot.artifact_contracts] == [
        "acme.echo.message"
    ]

    operation = snapshot.get_operation("acme.echo", "echo")
    assert operation is not None
    output = operation.spec.handler(
        operation.spec.input_model(message="hello packaged DLC"),
        DlcOperationContext(dlc_id="acme.echo", operation_name="echo"),
    )
    assert operation.spec.output_model.model_validate(output).model_dump() == {
        "message": "hello packaged DLC",
        "package_digest": built.package_digest,
    }

    update_inspection = service.inspect_from_file(built.update_archive)
    assert update_inspection.manifest.version == "2.0.0"
    assert update_inspection.package_digest == built.update_package_digest
    service.install_from_file(built.update_archive)
    installed = service.registry.get_installed_dlc("acme.echo")
    assert installed is not None
    assert installed.selected_digest == built.package_digest
    assert [item.package_digest for item in installed.installed_versions] == [
        built.package_digest,
        built.update_package_digest,
    ]
    assert marker_path.read_text(encoding="utf-8") == built.package_digest
    assert snapshot.active_dlcs[0].package_digest == built.package_digest

    service.select_package("acme.echo", built.update_package_digest)
    assert snapshot.active_dlcs[0].package_digest == built.package_digest
    assert marker_path.read_text(encoding="utf-8") == built.package_digest
