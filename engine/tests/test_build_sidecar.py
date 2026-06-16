import build_sidecar
import json
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
    assert "VITE_DATABOX_STATIC_TOKEN" not in env_text


def test_tauri_package_build_rebuilds_sidecar_before_frontend() -> None:
    config_path = Path(__file__).resolve().parents[2] / "desktop" / "src-tauri" / "tauri.conf.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    before_build = config["build"]["beforeBuildCommand"]

    assert "build_sidecar.py" in before_build
    assert before_build.index("build_sidecar.py") < before_build.index("npm run build")


def test_export_langsmith_runtime_env_copies_only_tracing_keys(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LANGCHAIN_TRACING_V2=true\n"
        "LANGCHAIN_API_KEY=lsv2-test\n"
        "LANGCHAIN_PROJECT=DataBox\n"
        "OPENAI_API_KEY=sk-should-not-copy\n",
        encoding="utf-8",
    )
    target = tmp_path / "runtime" / "config" / "langsmith.env"
    monkeypatch.setattr(build_sidecar, "private_runtime_file", lambda name, filename: target)

    result = build_sidecar.export_langsmith_runtime_env(env_file)

    assert result == target
    text = target.read_text(encoding="utf-8")
    assert "LANGCHAIN_TRACING_V2=true\n" in text
    assert "LANGCHAIN_API_KEY=lsv2-test\n" in text
    assert "LANGCHAIN_PROJECT=DataBox\n" in text
    assert "OPENAI_API_KEY" not in text
