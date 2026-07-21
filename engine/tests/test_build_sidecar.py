import build_sidecar
import json
import sys
from pathlib import Path


def test_write_env_local_uses_frontend_engine_env_names(tmp_path, monkeypatch) -> None:
    desktop_dir = tmp_path / "desktop"
    desktop_dir.mkdir()
    monkeypatch.setattr(build_sidecar, "DESKTOP_DIR", desktop_dir)

    path = build_sidecar.write_env_local("test-token")

    assert path == desktop_dir / ".env.local"
    env_text = path.read_text(encoding="utf-8")
    assert "VITE_LOCAL_ENGINE_PORT=18625\n" in env_text
    assert 'VITE_LOCAL_ENGINE_TOKEN="test-token"\n' in env_text
    assert "VITE_DBFOX_STATIC_TOKEN" not in env_text


def test_tauri_package_build_rebuilds_sidecar_before_frontend() -> None:
    config_path = Path(__file__).resolve().parents[2] / "desktop" / "src-tauri" / "tauri.conf.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    before_build = config["build"]["beforeBuildCommand"]

    assert "build_sidecar.py" in before_build
    assert before_build.index("build_sidecar.py") < before_build.index("npm run build")


def test_tauri_config_does_not_disable_platform_security_features() -> None:
    config_path = Path(__file__).resolve().parents[2] / "desktop" / "src-tauri" / "tauri.conf.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    browser_args = " ".join(
        window.get("additionalBrowserArgs", "")
        for window in config["app"].get("windows", [])
    )

    assert "msSmartScreenProtection" not in browser_args
    assert "--no-proxy-server" not in browser_args


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

    assert any(line.lower().startswith("pyyaml") for line in requirements.splitlines())
    assert any(line.startswith("openai") for line in requirements.splitlines())
    assert not any(line.startswith(("langgraph", "langchain", "langsmith")) for line in requirements.splitlines())
    assert "openai" in build_sidecar.HIDDEN_IMPORTS
    assert "langsmith" in build_sidecar.HIDDEN_IMPORTS


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
