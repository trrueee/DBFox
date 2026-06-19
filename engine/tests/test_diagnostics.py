from pathlib import Path

from fastapi.testclient import TestClient

from engine.main import LOCAL_SECURE_TOKEN, app


def test_redact_sensitive_text_masks_tokens_passwords_and_connection_strings() -> None:
    from engine.diagnostics.logs import redact_sensitive_text

    raw = "\n".join(
        [
            "OPENAI_API_KEY=sk-live-secret",
            "Authorization: Bearer bearer-secret",
            "password='plain-password'",
            "mysql://admin:db-password@127.0.0.1:3306/app",
            "normal message stays visible",
        ]
    )

    redacted = redact_sensitive_text(raw)

    assert "sk-live-secret" not in redacted
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
    assert body["sources"][0]["name"] == "engine"
    assert "secret-key" not in body["sources"][0]["content"]
    assert "api_key=[REDACTED]" in body["sources"][0]["content"]
