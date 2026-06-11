from __future__ import annotations

from typing import Any

from engine.llm.providers import openai as openai_provider


def test_openai_client_disables_provider_retries(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(openai_provider, "ChatOpenAI", FakeChatOpenAI)

    openai_provider.create_openai_client(
        model_name="gpt-test",
        api_key="sk-test",
        api_base="https://example.test/v1",
        timeout=12.0,
    )

    assert captured["timeout"] == 12.0
    assert captured["max_retries"] == 0
