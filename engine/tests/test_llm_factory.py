from __future__ import annotations

from typing import Any


def test_openai_client_disables_provider_retries(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    # Monkeypatch via the module where ChatOpenAI is actually imported at runtime
    monkeypatch.setattr("langchain_openai.ChatOpenAI", FakeChatOpenAI)

    from engine.llm.providers.openai import create_openai_client
    create_openai_client(
        model_name="gpt-test",
        api_key="sk-test",
        api_base="https://example.test/v1",
        timeout=12.0,
    )

    assert captured["timeout"] == 12.0
    assert captured["max_retries"] == 0
