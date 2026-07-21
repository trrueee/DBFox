from pathlib import Path

from fastapi.testclient import TestClient

from engine.main import LOCAL_SECURE_TOKEN, app


def test_redact_sensitive_text_masks_tokens_passwords_and_connection_strings() -> None:
    from engine.diagnostics.logs import redact_sensitive_text

    raw = "\n".join(
        [
            "OPENAI_API_KEY=TEST_LLM_SECRET",
            "Authorization: Bearer bearer-secret",
            "password='plain-password'",
            "mysql://admin:db-password@127.0.0.1:3306/app",
            "normal message stays visible",
        ]
    )

    redacted = redact_sensitive_text(raw)

    assert "TEST_LLM_SECRET" not in redacted
    assert "bearer-secret" not in redacted
    assert "plain-password" not in redacted
    assert "db-password" not in redacted
    assert "normal message stays visible" in redacted
    assert "[REDACTED]" in redacted


def test_read_log_source_returns_only_tail_and_redacts(tmp_path: Path) -> None:
    from engine.diagnostics.logs import read_log_source

    log_file = tmp_path / "engine.log"
    log_file.write_text(
        "\n".join(
            [
                "line 1",
                "line 2 password=secret-password",
                "line 3",
            ]
        ),
        encoding="utf-8",
    )

    source = read_log_source("engine", log_file, max_lines=2)

    assert source["name"] == "engine"
    assert source["exists"] is True
    assert source["content"] == "line 2 password=[REDACTED]\nline 3"
    assert "secret-password" not in source["content"]


def test_diagnostic_log_paths_stay_under_the_private_runtime_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from engine.diagnostics.logs import diagnostic_log_paths

    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("DBFOX_RUNTIME_DIR", str(runtime_root))

    for _name, path in diagnostic_log_paths():
        assert path.is_relative_to(runtime_root)


def test_diagnostics_logs_endpoint_returns_sanitized_sources(monkeypatch, tmp_path: Path) -> None:
    import engine.api.diagnostics as diagnostics_api

    log_file = tmp_path / "dbfox-engine.log"
    log_file.write_text("ERROR api_key=secret-key failed\n", encoding="utf-8")
    monkeypatch.setattr(diagnostics_api, "diagnostic_log_paths", lambda: [("engine", log_file)])

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/diagnostics/logs",
            headers={"X-Local-Token": LOCAL_SECURE_TOKEN},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["policy"]["redacted"] is True
    assert body["security_audit"]["retention_days"] == 90
    assert body["security_audit"]["export_window_days"] == 7
    assert body["sources"][0]["name"] == "engine"
    assert "secret-key" not in body["sources"][0]["content"]
    assert "api_key=[REDACTED]" in body["sources"][0]["content"]


def test_security_audit_clear_requires_explicit_confirmation() -> None:
    with TestClient(app) as client:
        rejected = client.post(
            "/api/v1/diagnostics/security-audit/clear",
            headers={"X-Local-Token": LOCAL_SECURE_TOKEN},
            json={"confirm_text": "clear"},
        )
        cleared = client.post(
            "/api/v1/diagnostics/security-audit/clear",
            headers={"X-Local-Token": LOCAL_SECURE_TOKEN},
            json={"confirm_text": "清空安全审计"},
        )

    assert rejected.status_code == 400
    assert rejected.json()["detail"]["code"] == "AUDIT_CLEAR_CONFIRMATION_REQUIRED"
    assert cleared.status_code == 200
    assert cleared.json()["cleared"] is True
