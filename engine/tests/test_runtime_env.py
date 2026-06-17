from __future__ import annotations


def test_load_runtime_env_reads_private_langsmith_env(tmp_path, monkeypatch):
    from engine.runtime_env import load_runtime_env

    runtime_root = tmp_path / "runtime"
    langsmith_env = runtime_root / "config" / "langsmith.env"
    langsmith_env.parent.mkdir(parents=True)
    langsmith_env.write_text(
        "LANGCHAIN_TRACING_V2=true\n"
        "LANGCHAIN_API_KEY=lsv2-test\n"
        "LANGCHAIN_PROJECT=DBFox Test\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DBFOX_RUNTIME_DIR", str(runtime_root))
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_PROJECT", raising=False)

    loaded = load_runtime_env(project_env=tmp_path / "missing.env")

    assert langsmith_env in loaded
    assert loaded.count(langsmith_env) == 1
    assert __import__("os").environ["LANGCHAIN_TRACING_V2"] == "true"
    assert __import__("os").environ["LANGCHAIN_API_KEY"] == "lsv2-test"
    assert __import__("os").environ["LANGCHAIN_PROJECT"] == "DBFox Test"
