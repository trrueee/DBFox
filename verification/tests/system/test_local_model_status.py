"""Read-only model status must not restart an unavailable local runtime."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.llm.endpoint_policy import ResolvedLlmEndpoint
from engine.llm.local_model import ManagedLocalModel


@pytest.mark.parametrize(("has_process", "exit_code", "closed", "available"), [
    (False, None, False, False),
    (True, None, False, True),
    (True, 7, False, False),
    (True, 0, False, False),
    (True, None, True, False),
])
def test_model_status_never_launches_or_restarts_a_process(
    tmp_path: Path, monkeypatch, has_process, exit_code, closed, available,
):
    profile_path = tmp_path / "local-model.json"
    profile_path.write_text(json.dumps({
        "model_name": "verification:local", "model_digest": "a" * 64,
        "model_size_bytes": 1, "executable": str(tmp_path / "ollama.exe"),
        "models_dir": str(tmp_path), "state_dir": str(tmp_path),
        "scratch_dir": str(tmp_path), "context_length": 32768,
    }), encoding="utf-8")
    model = ManagedLocalModel(profile_path)
    endpoint = ResolvedLlmEndpoint("http://127.0.0.1:12345/v1", "http", "127.0.0.1", 12345, ("127.0.0.1",))
    model._endpoint = endpoint
    model._process = SimpleNamespace(root_exit_code=lambda: exit_code) if has_process else None
    model._closed = closed

    def forbid_start(*_args):
        pytest.fail("A read-only status probe attempted to start a local model")

    monkeypatch.setattr(model, "endpoint", forbid_start)
    monkeypatch.setattr(model, "_start", forbid_start)
    assert model.running_endpoint() == (endpoint if available else None)
