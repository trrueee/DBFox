from __future__ import annotations

from engine.models import LLMLog


def test_llm_log_redacts_plaintext_prompt_and_response_by_default(db_session, monkeypatch) -> None:
    monkeypatch.delenv("DBFOX_ALLOW_LLM_PLAINTEXT_LOGS", raising=False)

    log = LLMLog(
        request_type="text_to_sql",
        prompt_hash="hash-1",
        prompt_text="schema contains customer email and password=secret",
        response_text="SELECT * FROM customers",
        model_name="test-model",
        status="success",
    )
    db_session.add(log)
    db_session.commit()

    saved = db_session.query(LLMLog).filter(LLMLog.id == log.id).one()

    assert saved.prompt_hash == "hash-1"
    assert saved.prompt_text is None
    assert saved.response_text is None


def test_llm_log_allows_plaintext_only_when_explicitly_enabled(db_session, monkeypatch) -> None:
    monkeypatch.setenv("DBFOX_ALLOW_LLM_PLAINTEXT_LOGS", "1")

    log = LLMLog(
        request_type="text_to_sql",
        prompt_text="safe local debug prompt",
        response_text="safe local debug response",
        model_name="test-model",
        status="success",
    )
    db_session.add(log)
    db_session.commit()

    saved = db_session.query(LLMLog).filter(LLMLog.id == log.id).one()

    assert saved.prompt_text == "safe local debug prompt"
    assert saved.response_text == "safe local debug response"
