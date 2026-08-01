from __future__ import annotations

from types import SimpleNamespace


def test_provider_disables_sdk_retries_and_owns_transport(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    monkeypatch.setattr(
        "engine.llm.providers.openai.resolve_runtime_llm_endpoint",
        lambda value: SimpleNamespace(api_base=value),
    )
    transport = object()
    monkeypatch.setattr(
        "engine.llm.providers.openai.get_llm_http_clients",
        lambda **_kwargs: (transport, object()),
    )

    from engine.llm.providers.openai import create_openai_responses_client

    create_openai_responses_client(
        api_key="secret",
        api_base="https://example.test/v1",
        timeout=12.0,
    )

    assert captured["max_retries"] == 0
    assert captured["http_client"] is transport
