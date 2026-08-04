import build_sidecar
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from scripts import verify_release_artifact


pytestmark = pytest.mark.platform_contract


def test_write_env_local_uses_frontend_engine_env_names(tmp_path, monkeypatch) -> None:
    desktop_dir = tmp_path / "desktop"
    desktop_dir.mkdir()
    monkeypatch.setattr(build_sidecar, "DESKTOP_DIR", desktop_dir)

    token = "a" * 64
    path = build_sidecar.write_env_local(token)

    assert path == desktop_dir / ".env.local"
    env_text = path.read_text(encoding="utf-8")
    assert "VITE_LOCAL_ENGINE_PORT=18625\n" in env_text
    assert f'VITE_LOCAL_ENGINE_TOKEN="{token}"\n' in env_text
    assert "VITE_DBFOX_STATIC_TOKEN" not in env_text


def test_dev_launchers_delegate_frontend_env_writes_to_one_helper() -> None:
    root = Path(__file__).resolve().parents[2]
    powershell_source = (root / "dev.ps1").read_text(encoding="utf-8")
    shell_source = (root / "dev.sh").read_text(encoding="utf-8")

    assert "scripts\\dev_environment.py" in powershell_source
    assert "scripts/dev_environment.py" in shell_source
    assert "WriteAllText" not in powershell_source
    assert ".env.local" not in powershell_source
    assert ".env.local" not in shell_source


def test_tauri_package_build_rebuilds_sidecar_before_frontend() -> None:
    config_path = Path(__file__).resolve().parents[2] / "desktop" / "src-tauri" / "tauri.conf.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    before_build = config["build"]["beforeBuildCommand"]

    assert "build_sidecar.py" in before_build
    assert before_build.index("build_sidecar.py") < before_build.index("npm run build")
    assert config["bundle"]["resources"]["binaries/dbfox-engine-runtime-manifest.json"] == "dbfox-engine-runtime-manifest.json"


def _runtime_manifest(version: tuple[int, int, int]) -> dict[str, object]:
    return {
        "schema_version": 2,
        "frozen": True,
        "python_version": build_sidecar.sidecar_python_version(),
        "build_python_version": build_sidecar.sidecar_python_version(),
        "build_lock_file": build_sidecar.BUILD_LOCK.name,
        "build_lock_sha256": build_sidecar._sha256(build_sidecar.BUILD_LOCK),
        "build_packages": {
            name: "test-version" for name in build_sidecar.KEY_BUILD_PACKAGES
        },
        "sqlite_version": ".".join(map(str, version)),
        "sqlite_version_info": list(version),
        "sqlite_source_id": f"{'.'.join(map(str, version))} source-id",
        "sqlite_compile_options": ["THREADSAFE=1"],
    }


def test_runtime_manifest_gate_rejects_last_affected_sqlite() -> None:
    with pytest.raises(RuntimeError, match=r"minimum is 3\.51\.3"):
        build_sidecar.validate_runtime_manifest(_runtime_manifest((3, 51, 2)))


def test_runtime_manifest_gate_accepts_fixed_sqlite() -> None:
    build_sidecar.validate_runtime_manifest(_runtime_manifest((3, 51, 3)))


def test_artifact_manifest_binds_runtime_to_sidecar_hash(tmp_path, monkeypatch) -> None:
    binary = tmp_path / "dbfox-engine-test"
    binary.write_bytes(b"final-sidecar")
    output = tmp_path / "runtime-manifest.json"
    monkeypatch.setattr(build_sidecar, "RUNTIME_MANIFEST_PATH", output)
    monkeypatch.setattr(build_sidecar, "get_target_triplet", lambda: "test-triplet")

    result = build_sidecar.write_artifact_manifest(binary, _runtime_manifest((3, 53, 4)))
    manifest = json.loads(result.read_text(encoding="utf-8"))

    assert manifest["target_triplet"] == "test-triplet"
    assert manifest["sidecar_filename"] == binary.name
    assert manifest["sidecar_sha256"] == "3d3e01030d00b413489c82ee644fdfac09c83dd4b21aeacd9feeea8caa4f1c5f"
    assert manifest["minimum_sqlite_version"] == "3.51.3"
    assert manifest["target_sqlite_version"] == "3.53.4"
    assert manifest["schema_version"] == build_sidecar.ARTIFACT_MANIFEST_SCHEMA_VERSION


def test_extracted_installer_must_match_manifest_hash_and_runtime(tmp_path, monkeypatch) -> None:
    root = tmp_path / "installer"
    root.mkdir()
    sidecar = root / ("dbfox-engine.exe" if sys.platform == "win32" else "dbfox-engine")
    sidecar.write_bytes(b"installed-sidecar")
    runtime = _runtime_manifest((3, 53, 4))
    manifest = {
        "schema_version": build_sidecar.ARTIFACT_MANIFEST_SCHEMA_VERSION,
        "target_triplet": "test-triplet",
        "sidecar_sha256": build_sidecar._sha256(sidecar),
        "runtime": runtime,
    }
    expected_manifest = tmp_path / "expected.json"
    expected_manifest.write_text(json.dumps(manifest), encoding="utf-8")
    (root / "dbfox-engine-runtime-manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    monkeypatch.setattr(build_sidecar, "probe_sidecar_runtime", lambda _path: runtime)

    result = verify_release_artifact.verify_extracted_tree(root, expected_manifest)

    assert result["verified"] is True
    assert result["sqlite_version"] == runtime["sqlite_version"]
    assert result["sidecar_size_bytes"] == len(b"installed-sidecar")
    assert result["package_files_scanned"] == 2
    assert result["forbidden_file_hits"] == 0
    assert result["forbidden_value_hits"] == 0


def test_extracted_installer_rejects_release_token_sentinel(tmp_path, monkeypatch) -> None:
    root = tmp_path / "installer"
    root.mkdir()
    sidecar = root / ("dbfox-engine.exe" if sys.platform == "win32" else "dbfox-engine")
    sidecar.write_bytes(b"installed-sidecar")
    runtime = _runtime_manifest((3, 53, 4))
    manifest = {
        "schema_version": build_sidecar.ARTIFACT_MANIFEST_SCHEMA_VERSION,
        "target_triplet": "test-triplet",
        "sidecar_sha256": build_sidecar._sha256(sidecar),
        "runtime": runtime,
    }
    expected_manifest = tmp_path / "expected.json"
    expected_manifest.write_text(json.dumps(manifest), encoding="utf-8")
    (root / "dbfox-engine-runtime-manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    (root / "frontend.js").write_bytes(b"prefix-dbfox-release-sentinel-1234567890-suffix")
    monkeypatch.setattr(build_sidecar, "probe_sidecar_runtime", lambda _path: runtime)

    with pytest.raises(RuntimeError, match="forbidden production value"):
        verify_release_artifact.verify_extracted_tree(
            root,
            expected_manifest,
            forbidden_values=(b"dbfox-release-sentinel-1234567890",),
        )


def test_extracted_installer_rejects_development_files(tmp_path, monkeypatch) -> None:
    root = tmp_path / "installer"
    root.mkdir()
    sidecar = root / ("dbfox-engine.exe" if sys.platform == "win32" else "dbfox-engine")
    sidecar.write_bytes(b"installed-sidecar")
    runtime = _runtime_manifest((3, 53, 4))
    manifest = {
        "schema_version": build_sidecar.ARTIFACT_MANIFEST_SCHEMA_VERSION,
        "target_triplet": "test-triplet",
        "sidecar_sha256": build_sidecar._sha256(sidecar),
        "runtime": runtime,
    }
    expected_manifest = tmp_path / "expected.json"
    expected_manifest.write_text(json.dumps(manifest), encoding="utf-8")
    (root / "dbfox-engine-runtime-manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    (root / ".env.local").write_text("VITE_LOCAL_ENGINE_TOKEN=forbidden", encoding="utf-8")
    monkeypatch.setattr(build_sidecar, "probe_sidecar_runtime", lambda _path: runtime)

    with pytest.raises(RuntimeError, match="forbidden development files"):
        verify_release_artifact.verify_extracted_tree(root, expected_manifest)


def test_frozen_smoke_uses_rustc_host_tuple_without_platform_mapping() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / "desktop" / "scripts" / "smoke-sidecar.mjs").read_text(encoding="utf-8")

    assert '["--print", "host-tuple"]' in source
    assert "x86_64-pc-windows-msvc" not in source
    assert "x86_64-unknown-linux-gnu" not in source
    assert "aarch64-apple-darwin" not in source


def test_frozen_smoke_covers_schema_result_artifact_and_restart_contracts() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / "desktop" / "scripts" / "smoke-sidecar.mjs").read_text(
        encoding="utf-8"
    )

    for contract in (
        "/api/v1/datasources/${datasource.id}/sync",
        "/api/v1/agent/console/execute",
        "/api/v1/artifacts/${first.resultArtifactId}/page",
        "/api/v1/conversations/${sessionId}",
        "stale_token_rejected",
        "restart_reload",
    ):
        assert contract in source


def test_packaged_sidecar_preserves_control_stream_without_showing_a_window() -> None:
    root = Path(__file__).resolve().parents[2]
    builder_source = Path(build_sidecar.__file__).read_text(encoding="utf-8")
    process_source = (root / "desktop" / "src-tauri" / "src" / "sidecar_process.rs").read_text(
        encoding="utf-8"
    )
    cargo = (root / "desktop" / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")

    assert '"--console"' in builder_source
    assert '"--noconsole"' not in builder_source
    assert 'tauri-plugin-shell = "2.3.5"' in cargo
    assert '.sidecar("dbfox-engine")' in process_source
    assert "CommandEvent::Stdout" in process_source
    assert "CommandEvent::Stderr" in process_source
    assert "CommandEvent::Terminated" in process_source
    assert "sidecar_candidate_paths" not in process_source


def test_webview_does_not_receive_shell_process_permissions() -> None:
    root = Path(__file__).resolve().parents[2] / "desktop" / "src-tauri" / "capabilities"
    permissions = []
    for path in root.glob("*.json"):
        permissions.extend(json.loads(path.read_text(encoding="utf-8"))["permissions"])

    assert not any(permission.startswith("shell:") for permission in permissions)


def test_tauri_config_does_not_disable_platform_security_features() -> None:
    config_path = Path(__file__).resolve().parents[2] / "desktop" / "src-tauri" / "tauri.conf.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    browser_args = " ".join(
        window.get("additionalBrowserArgs", "")
        for window in config["app"].get("windows", [])
    )

    assert "msSmartScreenProtection" not in browser_args
    assert "--no-proxy-server" not in browser_args


def test_tauri_app_commands_have_explicit_main_window_permissions() -> None:
    root = Path(__file__).resolve().parents[2]
    tauri_root = root / "desktop" / "src-tauri"
    build_source = (tauri_root / "build.rs").read_text(encoding="utf-8")
    capabilities = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in (tauri_root / "capabilities").glob("*.json")
    }

    declared_commands = set(re.findall(r'^\s*"([a-z_]+)",?$', build_source, re.MULTILINE))
    command_permission_sets = {
        name: {permission for permission in capability["permissions"] if permission.startswith("allow-")}
        for name, capability in capabilities.items()
    }
    command_permissions = set().union(*command_permission_sets.values())
    allowed_commands = {
        permission.removeprefix("allow-").replace("-", "_")
        for permission in command_permissions
    }

    assert declared_commands == allowed_commands
    assert all(capability["windows"] == ["main"] for capability in capabilities.values())
    assert sum(len(permissions) for permissions in command_permission_sets.values()) == len(command_permissions)
    assert not command_permission_sets["default"]
    assert not any(
        permission.startswith("opener:")
        for capability in capabilities.values()
        for permission in capability["permissions"]
    )


def test_sidecar_builder_has_no_langsmith_plaintext_export_path() -> None:
    source = Path(build_sidecar.__file__).read_text(encoding="utf-8")

    assert not hasattr(build_sidecar, "export_langsmith_runtime_env")
    assert "langsmith.env" not in source
    assert "LANGCHAIN_" not in source
    assert "LANGSMITH_" not in source


def test_duckdb_runtime_dependency_and_sidecar_import_are_declared() -> None:
    root = Path(__file__).resolve().parents[2]
    requirements = (root / "requirements.txt").read_text(encoding="utf-8")

    assert any(line.startswith("duckdb") for line in requirements.splitlines())
    assert "duckdb" in build_sidecar.HIDDEN_IMPORTS


def test_dynamic_runtime_dependencies_are_declared_for_the_frozen_sidecar() -> None:
    root = Path(__file__).resolve().parents[2]
    requirements = (root / "requirements.txt").read_text(encoding="utf-8")

    assert any(line.startswith("openai") for line in requirements.splitlines())
    assert not any(line.startswith(("langgraph", "langchain", "langsmith")) for line in requirements.splitlines())
    assert "openai" in build_sidecar.HIDDEN_IMPORTS
    assert "langsmith" not in build_sidecar.HIDDEN_IMPORTS


def test_supported_sqlglot_dialects_are_declared_as_frozen_hidden_imports() -> None:
    assert {
        "sqlglot.dialects.mysql",
        "sqlglot.dialects.postgres",
        "sqlglot.dialects.sqlite",
    }.issubset(build_sidecar.HIDDEN_IMPORTS)


def test_sidecar_build_dependencies_are_separate_from_runtime_dependencies() -> None:
    root = Path(__file__).resolve().parents[2]
    requirements = (root / "requirements-build.txt").read_text(encoding="utf-8")

    assert "-r requirements.txt" in requirements
    assert any(line.startswith("pyinstaller") for line in requirements.lower().splitlines())


def test_removed_local_crypto_is_not_a_direct_runtime_dependency() -> None:
    root = Path(__file__).resolve().parents[2]
    requirements = (root / "requirements.txt").read_text(encoding="utf-8")
    development_requirements = (root / "requirements-dev.txt").read_text(encoding="utf-8")

    assert not any(line.startswith("cryptography") for line in requirements.splitlines())
    assert "types-cryptography" not in development_requirements
    assert "cryptography" not in build_sidecar.HIDDEN_IMPORTS
    assert not (root / "engine" / "crypto.py").exists()


def test_token_only_does_not_write_production_static_token(monkeypatch, tmp_path) -> None:
    def fail_static_token_write(_token: str) -> Path:
        raise AssertionError("production static token preset must not be generated")

    monkeypatch.setattr(build_sidecar, "write_token_preset", fail_static_token_write, raising=False)
    monkeypatch.setattr(build_sidecar, "write_env_local", lambda _token: tmp_path / ".env.local")
    monkeypatch.setattr(sys, "argv", ["build_sidecar.py", "--token-only"])

    build_sidecar.main()


def test_target_triplet_uses_rustc_host_tuple(monkeypatch) -> None:
    observed: list[list[str]] = []

    def run(command, **_kwargs):
        observed.append(command)
        return subprocess.CompletedProcess(command, 0, "aarch64-apple-darwin\n", "")

    monkeypatch.setattr(build_sidecar.subprocess, "run", run)

    assert build_sidecar.get_target_triplet() == "aarch64-apple-darwin"
    assert observed == [["rustc", "--print", "host-tuple"]]


def test_target_triplet_fails_closed_when_rustc_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        build_sidecar.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 1, "", "toolchain missing"),
    )

    with pytest.raises(RuntimeError, match=r"rustc --print host-tuple.*exit=1"):
        build_sidecar.get_target_triplet()


def test_release_sync_requires_uv(monkeypatch, tmp_path, capsys) -> None:
    lock = tmp_path / "requirements-build.lock"
    lock.write_text("", encoding="utf-8")
    monkeypatch.setattr(build_sidecar, "BUILD_LOCK", lock)
    monkeypatch.setattr(build_sidecar.shutil, "which", lambda _name: None)

    with pytest.raises(SystemExit) as exit_info:
        build_sidecar.sync_build_environment("python")

    assert exit_info.value.code == 1
    assert "Release builds require uv" in capsys.readouterr().err


def test_release_sync_uses_uv_exact_environment_semantics(monkeypatch, tmp_path, capsys) -> None:
    lock = tmp_path / "requirements-build.lock"
    lock.write_text("", encoding="utf-8")
    observed: list[list[str]] = []
    monkeypatch.setattr(build_sidecar, "BUILD_LOCK", lock)
    monkeypatch.setattr(build_sidecar.shutil, "which", lambda _name: "uv")

    def run(command, **_kwargs):
        observed.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(build_sidecar.subprocess, "run", run)

    build_sidecar.sync_build_environment("clean-build-python")

    assert observed == [[
        "uv",
        "pip",
        "sync",
        str(lock),
        "--python",
        "clean-build-python",
    ]]
    assert "Synced" in capsys.readouterr().out


def test_sidecar_python_version_is_an_exact_repository_pin() -> None:
    version = build_sidecar.sidecar_python_version()

    assert re.fullmatch(r"\d+\.\d+\.\d+", version)


def test_build_provenance_rejects_a_different_interpreter(
    monkeypatch,
    tmp_path,
) -> None:
    lock = tmp_path / "requirements-build.lock"
    lock.write_text("locked", encoding="utf-8")
    monkeypatch.setattr(build_sidecar, "BUILD_LOCK", lock)
    monkeypatch.setattr(
        build_sidecar,
        "_build_environment_facts",
        lambda _python: {
            "python_version": "0.0.0",
            "packages": {name: "1" for name in build_sidecar.KEY_BUILD_PACKAGES},
        },
    )

    with pytest.raises(RuntimeError, match="does not match the production pin"):
        build_sidecar.collect_build_provenance("wrong-python")


def test_staged_engine_contains_build_provenance(tmp_path) -> None:
    provenance = {
        "schema_version": 1,
        "python_version": build_sidecar.sidecar_python_version(),
        "lock_file": "requirements-build.lock",
        "lock_sha256": "a" * 64,
        "packages": {name: "1" for name in build_sidecar.KEY_BUILD_PACKAGES},
    }

    staged = build_sidecar.prepare_sidecar_engine_tree(tmp_path, provenance)
    written = json.loads(
        (staged / build_sidecar.BUILD_PROVENANCE_FILENAME).read_text(encoding="utf-8")
    )

    assert written == provenance


def test_release_build_never_writes_frontend_dev_token(monkeypatch, tmp_path) -> None:
    binary = tmp_path / "dbfox-engine"
    binary.write_bytes(b"sidecar")
    monkeypatch.setattr(build_sidecar, "_venv_python", lambda: "python")
    monkeypatch.setattr(build_sidecar, "sync_build_environment", lambda _python: None)
    monkeypatch.setattr(build_sidecar, "build_pyinstaller", lambda _python: binary)
    monkeypatch.setattr(build_sidecar, "install_sidecar", lambda source: source)
    monkeypatch.setattr(build_sidecar, "probe_sidecar_runtime", lambda _binary: _runtime_manifest((3, 53, 4)))
    monkeypatch.setattr(build_sidecar, "write_artifact_manifest", lambda *_args: tmp_path / "manifest.json")
    monkeypatch.setattr(
        build_sidecar,
        "write_env_local",
        lambda _token: (_ for _ in ()).throw(AssertionError("release wrote .env.local")),
    )
    monkeypatch.setattr(sys, "argv", ["build_sidecar.py"])

    build_sidecar.main()
