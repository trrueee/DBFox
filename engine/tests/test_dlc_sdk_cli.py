"""Conformance tests for the product DLC builder and CLI."""

from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from engine.dlc.cli import main
from engine.dlc.errors import DlcError, DlcErrorCode
from engine.dlc.package_builder import build_dlc_package
from engine.dlc.trust import DlcTrustStore
from engine.dlc.verifier import DlcPackageVerifier
from engine.tests.fixtures.dlc_fixture_builder import (
    build_test_dlc_archive,
    generate_test_keypair,
)


def test_cli_init_build_test_is_deterministic_and_registry_isolated(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    source = tmp_path / "source"
    private_key = tmp_path / "keys" / "publisher.pem"
    monkeypatch.setenv("DBFOX_DLC_TEST_PASSWORD", "correct horse battery staple")
    assert main(
        [
            "init",
            str(source),
            "--id",
            "acme.conformance",
            "--publisher",
            "acme",
            "--generate-key",
            str(private_key),
            "--key-password-env",
            "DBFOX_DLC_TEST_PASSWORD",
        ]
    ) == 0
    init_output = capsys.readouterr().out
    assert "PRIVATE KEY" not in init_output
    assert private_key.is_file()
    public_key = private_key.with_suffix(private_key.suffix + ".pub")

    first = tmp_path / "first.dbfox-dlc"
    second = tmp_path / "second.dbfox-dlc"
    build_args = [
        "build",
        str(source),
        "--private-key",
        str(private_key),
        "--key-password-env",
        "DBFOX_DLC_TEST_PASSWORD",
    ]
    assert main([*build_args, "--output", str(first)]) == 0
    first_output = capsys.readouterr().out
    assert main([*build_args, "--output", str(second)]) == 0
    capsys.readouterr()
    assert first.read_bytes() == second.read_bytes()
    assert private_key.read_bytes() not in first.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert not any("key" in name.lower() for name in archive.namelist())

    runtime_root = tmp_path / "must-not-exist" / "installed-registry"
    monkeypatch.setenv("DBFOX_RUNTIME_DIR", str(runtime_root))
    assert main(["test", str(first)]) == 0
    test_output = json.loads(capsys.readouterr().out)
    assert test_output["registry_modified"] is False
    assert test_output["python_files_checked"] == 1
    assert test_output["javascript_files_checked"] == 1
    assert not runtime_root.exists()
    assert "PRIVATE KEY" not in first_output
    assert public_key.is_file()


def test_offline_signing_matches_direct_deterministic_build(
    tmp_path: Path,
    capsys,
) -> None:
    source = tmp_path / "source"
    private_key = tmp_path / "publisher.pem"
    assert main(
        [
            "init",
            str(source),
            "--id",
            "acme.offline",
            "--publisher",
            "acme",
            "--generate-key",
            str(private_key),
            "--unencrypted-key",
        ]
    ) == 0
    capsys.readouterr()
    public_key = private_key.with_suffix(private_key.suffix + ".pub")
    unsigned = tmp_path / "unsigned.dbfox-dlc"
    signed = tmp_path / "signed.dbfox-dlc"
    direct = tmp_path / "direct.dbfox-dlc"
    assert main(
        [
            "build",
            str(source),
            "--unsigned",
            "--public-key",
            str(public_key),
            "--output",
            str(unsigned),
        ]
    ) == 0
    capsys.readouterr()
    assert main(
        [
            "sign",
            str(unsigned),
            "--private-key",
            str(private_key),
            "--output",
            str(signed),
        ]
    ) == 0
    capsys.readouterr()
    assert main(
        [
            "build",
            str(source),
            "--private-key",
            str(private_key),
            "--output",
            str(direct),
        ]
    ) == 0
    capsys.readouterr()
    assert signed.read_bytes() == direct.read_bytes()


def test_sign_rejects_a_key_that_does_not_match_unsigned_manifest(
    tmp_path: Path,
    capsys,
) -> None:
    source = tmp_path / "source"
    first_key = tmp_path / "first.pem"
    second_key = tmp_path / "second.pem"
    assert main(
        [
            "init",
            str(source),
            "--id",
            "acme.mismatch",
            "--publisher",
            "acme",
            "--generate-key",
            str(first_key),
            "--unencrypted-key",
        ]
    ) == 0
    capsys.readouterr()
    assert main(
        [
            "init",
            str(tmp_path / "other"),
            "--id",
            "acme.other",
            "--publisher",
            "acme",
            "--generate-key",
            str(second_key),
            "--unencrypted-key",
        ]
    ) == 0
    capsys.readouterr()
    unsigned = tmp_path / "unsigned.dbfox-dlc"
    assert main(
        [
            "build",
            str(source),
            "--unsigned",
            "--output",
            str(unsigned),
        ]
    ) == 0
    capsys.readouterr()
    assert main(
        [
            "sign",
            str(unsigned),
            "--private-key",
            str(second_key),
            "--output",
            str(tmp_path / "must-not-exist.dbfox-dlc"),
        ]
    ) == 1
    assert "does not match" in capsys.readouterr().err


def test_product_builder_rejects_native_payloads_and_embedded_react() -> None:
    private_key = ed25519.Ed25519PrivateKey.generate()
    manifest = {
        "manifestSchemaVersion": 2,
        "id": "acme.contract",
        "version": "1.0.0",
        "displayName": "Contract",
        "publisher": "acme",
        "extensionApiVersion": "2",
        "requiresDbfox": ">=1.0.0",
        "entrypoints": {"backend": None, "frontend": "frontend/index.js"},
        "permissions": [],
    }
    try:
        build_dlc_package(
            manifest,
            {
                "frontend/index.js": "export function register(host) {}",
                "backend/native.node": b"native",
            },
            private_key=private_key,
        )
    except Exception as exc:
        assert "Native binary extension" in str(exc)
    else:
        raise AssertionError("native extension was accepted")

    try:
        build_dlc_package(
            manifest,
            {
                "frontend/index.js": (
                    "const __SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED = {};"
                    " export function register(host) {}"
                )
            },
            private_key=private_key,
        )
    except Exception as exc:
        assert "embeds a React runtime" in str(exc)
    else:
        raise AssertionError("embedded React runtime was accepted")


def test_host_verifier_enforces_the_same_frontend_react_contract() -> None:
    private_key, public_key_base64 = generate_test_keypair()
    archive = build_test_dlc_archive(
        payload_files={
            "backend/entry.py": "def register(host):\n    pass\n",
            "frontend/index.js": (
                "const __SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED = {};"
                " export function register(host) {}"
            ),
        },
        private_key=private_key,
    )
    verifier = DlcPackageVerifier(DlcTrustStore({"fixture": public_key_base64}))
    with pytest.raises(DlcError) as exc_info:
        verifier.verify_archive_bytes(
            archive,
            publisher_key_base64=public_key_base64,
        )
    assert exc_info.value.code == DlcErrorCode.INVALID_ARCHIVE


def test_cli_test_rejects_tampered_signed_package(
    tmp_path: Path,
    capsys,
) -> None:
    private_key = ed25519.Ed25519PrivateKey.generate()
    built = build_dlc_package(
        {
            "manifestSchemaVersion": 2,
            "id": "acme.tampered",
            "version": "1.0.0",
            "displayName": "Tampered",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py", "frontend": None},
            "permissions": [],
        },
        {"backend/entry.py": "def register(host):\n    pass\n"},
        private_key=private_key,
    )
    package = tmp_path / "tampered.dbfox-dlc"
    tampered_bytes = bytearray(built.archive_bytes)
    payload_offset = tampered_bytes.index(b"def register")
    tampered_bytes[payload_offset] ^= 1
    package.write_bytes(tampered_bytes)
    assert main(["test", str(package)]) == 1
    assert capsys.readouterr().err.startswith("dbfox-dlc:")
