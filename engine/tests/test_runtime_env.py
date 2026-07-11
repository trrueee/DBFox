from __future__ import annotations

import os


def test_load_runtime_env_never_reads_private_runtime_config_files(tmp_path, monkeypatch):
    from engine.runtime_env import load_runtime_env

    runtime_root = tmp_path / "runtime"
    langsmith_env = runtime_root / "config" / "langsmith.env"
    private_env = runtime_root / "config" / ".env"
    langsmith_env.parent.mkdir(parents=True)
    langsmith_env.write_text(
        "LANGCHAIN_TRACING_V2=true\n"
        "LANGCHAIN_API_KEY=lsv2-test\n"
        "DBFOX_ENGINE_PORT=29999\n",
        encoding="utf-8",
    )
    private_env.write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")

    monkeypatch.setenv("DBFOX_RUNTIME_DIR", str(runtime_root))
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.delenv("DBFOX_ENGINE_PORT", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    loaded = load_runtime_env(project_env=tmp_path / "missing.env")

    assert loaded == []
    assert "LANGCHAIN_TRACING_V2" not in os.environ
    assert "LANGCHAIN_API_KEY" not in os.environ
    assert "OPENAI_API_KEY" not in os.environ
    assert "DBFOX_ENGINE_PORT" not in os.environ


def test_load_runtime_env_loads_configuration_but_rejects_plaintext_credentials(
    tmp_path,
    monkeypatch,
):
    from engine.runtime_env import load_runtime_env

    project_env = tmp_path / ".env"
    project_env.write_text(
        "DBFOX_ENGINE_PORT=29999\n"
        "DBFOX_DATABASE_URL=sqlite:///safe.db\n"
        "OPENAI_API_KEY=sk-test\n"
        "LANGCHAIN_API_KEY=lsv2-test\n"
        "LANGSMITH_PROJECT=should-not-load\n"
        "CUSTOM_PROVIDER_API_KEY=provider-secret\n"
        "DBFOX_ENGINE_TOKEN=engine-secret\n",
        encoding="utf-8",
    )
    for name in (
        "DBFOX_ENGINE_PORT",
        "DBFOX_DATABASE_URL",
        "OPENAI_API_KEY",
        "LANGCHAIN_API_KEY",
        "LANGSMITH_PROJECT",
        "CUSTOM_PROVIDER_API_KEY",
        "DBFOX_ENGINE_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)

    loaded = load_runtime_env(project_env=project_env)

    assert loaded == [project_env]
    assert os.environ["DBFOX_ENGINE_PORT"] == "29999"
    assert os.environ["DBFOX_DATABASE_URL"] == "sqlite:///safe.db"
    for name in (
        "OPENAI_API_KEY",
        "LANGCHAIN_API_KEY",
        "LANGSMITH_PROJECT",
        "CUSTOM_PROVIDER_API_KEY",
        "DBFOX_ENGINE_TOKEN",
    ):
        assert name not in os.environ
