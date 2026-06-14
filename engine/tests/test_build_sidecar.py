import build_sidecar


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
