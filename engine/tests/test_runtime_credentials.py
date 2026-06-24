from __future__ import annotations

import pytest

from engine.engine_runtime.credentials import MissingEngineTokenError, RuntimeCredentialPolicy


def test_frozen_runtime_requires_env_token(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("DBFOX_ENGINE_TOKEN", raising=False)

    policy = RuntimeCredentialPolicy(token_file=tmp_path / ".local_token", is_frozen=True)

    with pytest.raises(MissingEngineTokenError, match="DBFOX_ENGINE_TOKEN"):
        policy.resolve_token()


def test_frozen_runtime_uses_env_token(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DBFOX_ENGINE_TOKEN", " runtime-token ")

    policy = RuntimeCredentialPolicy(token_file=tmp_path / ".local_token", is_frozen=True)

    assert policy.resolve_token() == "runtime-token"


def test_dev_runtime_reuses_local_token_file(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("DBFOX_ENGINE_TOKEN", raising=False)
    token_file = tmp_path / ".local_token"
    token_file.write_text("dev-token\n", encoding="utf-8")

    policy = RuntimeCredentialPolicy(token_file=token_file, is_frozen=False)

    assert policy.resolve_token() == "dev-token"


def test_dev_runtime_generates_and_persists_local_token(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("DBFOX_ENGINE_TOKEN", raising=False)
    monkeypatch.setattr("engine.engine_runtime.credentials.secrets.token_hex", lambda size: "a" * (size * 2))
    token_file = tmp_path / ".local_token"

    policy = RuntimeCredentialPolicy(token_file=token_file, is_frozen=False)

    assert policy.resolve_token() == "a" * 64
    assert token_file.read_text(encoding="utf-8") == "a" * 64
