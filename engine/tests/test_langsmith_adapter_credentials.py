from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import engine.evaluation.langsmith_adapter as langsmith_adapter
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault


def test_langsmith_adapter_does_not_use_process_environment_credentials(
    monkeypatch,
) -> None:
    class Client:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("a vault credential reference is required")

    fake_langsmith = ModuleType("langsmith")
    fake_langsmith.Client = Client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langsmith", fake_langsmith)
    monkeypatch.setenv("LANGCHAIN_API_KEY", "plaintext-env-secret")
    monkeypatch.setenv("LANGSMITH_API_KEY", "plaintext-env-secret")

    adapter = langsmith_adapter.LangSmithAdapter()

    assert adapter.available is False


def test_langsmith_adapter_resolves_an_explicit_vault_credential_at_runtime(
    monkeypatch,
) -> None:
    captured: list[dict[str, Any]] = []

    class Client:
        def __init__(self, **kwargs: Any) -> None:
            captured.append(kwargs)

    fake_langsmith = ModuleType("langsmith")
    fake_langsmith.Client = Client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langsmith", fake_langsmith)
    monkeypatch.setenv("LANGCHAIN_API_KEY", "wrong-env-secret")

    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.LANGSMITH_API_KEY,
        secret="vault-langsmith-secret",
    )
    adapter = langsmith_adapter.LangSmithAdapter(
        credential_id=credential_id,
        credential_vault=vault,
        endpoint="https://langsmith.example.test",
    )

    assert adapter.available is True
    assert captured == [
        {
            "api_key": "vault-langsmith-secret",
            "api_url": "https://langsmith.example.test",
        }
    ]


def test_langsmith_adapter_rejects_an_opaque_reference_of_the_wrong_kind(
    monkeypatch,
) -> None:
    class Client:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("wrong credential kind must not reach provider")

    fake_langsmith = ModuleType("langsmith")
    fake_langsmith.Client = Client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langsmith", fake_langsmith)

    vault = InMemoryCredentialVault()
    llm_credential_id = vault.put(
        kind=CredentialKind.LLM_API_KEY,
        secret="llm-secret",
    )
    adapter = langsmith_adapter.LangSmithAdapter(
        credential_id=llm_credential_id,
        credential_vault=vault,
    )

    assert adapter.available is False
