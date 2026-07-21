from __future__ import annotations

import sys
from types import ModuleType
from types import SimpleNamespace
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
    monkeypatch.setattr(
        langsmith_adapter,
        "validate_runtime_llm_api_base",
        lambda endpoint: endpoint,
    )

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
    monkeypatch.setattr(
        langsmith_adapter,
        "validate_runtime_llm_api_base",
        lambda endpoint: endpoint,
    )

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


def test_langsmith_adapter_rejects_an_unsafe_endpoint_before_reading_the_vault(
    monkeypatch,
) -> None:
    class NeverReadVault:
        def get(self, *_args: Any, **_kwargs: Any) -> str:
            raise AssertionError("unsafe endpoint must be rejected before vault access")

    class UnexpectedClient:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("unsafe endpoint must not construct a provider client")

    fake_langsmith = ModuleType("langsmith")
    fake_langsmith.Client = UnexpectedClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langsmith", fake_langsmith)

    adapter = langsmith_adapter.LangSmithAdapter(
        credential_id="cred_langsmith_api_key_test",
        credential_vault=NeverReadVault(),  # type: ignore[arg-type]
        endpoint="https://127.0.0.1/api",
    )

    assert adapter.available is False


def test_import_annotated_failures_builds_deterministic_cases_from_human_feedback(
    monkeypatch,
) -> None:
    runs = [
        SimpleNamespace(
            id="run-failed",
            inputs={"question": "Which customers churned?", "workspace_context": {"tables": ["users"]}},
            extra={"metadata": {"eval_category": "data_lookup"}},
            tags=["production-review"],
            error=None,
        ),
        SimpleNamespace(
            id="run-model-only",
            inputs={"question": "Ignore model-only feedback"},
            extra={},
            tags=[],
            error=None,
        ),
    ]
    feedback = [
        SimpleNamespace(
            run_id="run-failed",
            key="correctness",
            score=0,
            value=None,
            correction={
                "category": "sql_generation",
                "description": "Regression from reviewer correction",
                "expected": {"sql": {"contains_keywords": ["WHERE"]}},
            },
            feedback_source={"type": "api", "user_name": "reviewer"},
        ),
        SimpleNamespace(
            run_id="run-model-only",
            key="model-judge",
            score=0,
            value=None,
            correction=None,
            feedback_source={"type": "model"},
        ),
    ]

    class Client:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def list_runs(self, **kwargs: Any):
            assert kwargs["project_name"] == "reviewed-project"
            return iter(runs)

        def list_feedback(self, **kwargs: Any):
            assert set(kwargs["run_ids"]) == {"run-failed", "run-model-only"}
            return iter(feedback)

    fake_langsmith = ModuleType("langsmith")
    fake_langsmith.Client = Client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langsmith", fake_langsmith)
    monkeypatch.setattr(langsmith_adapter, "validate_runtime_llm_api_base", lambda endpoint: endpoint)
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.LANGSMITH_API_KEY,
        secret="vault-langsmith-secret",
    )

    cases = langsmith_adapter.LangSmithAdapter(
        credential_id=credential_id,
        credential_vault=vault,
    ).import_annotated_failures("reviewed-project")

    assert [case.id for case in cases] == ["langsmith_run-failed"]
    case = cases[0]
    assert case.category == "sql_generation"
    assert case.input.question == "Which customers churned?"
    assert case.expected.sql is not None
    assert case.expected.sql.contains_keywords == ["WHERE"]
    assert case.metadata["feedback_keys"] == ["correctness"]
    assert case.tags == ["annotated-failure", "langsmith-import", "production-review"]


def test_import_annotated_failures_uses_safe_default_expectation_without_correction(
    monkeypatch,
) -> None:
    run = SimpleNamespace(
        id="run-no-correction",
        inputs={"question": "Explain this result"},
        extra={},
        tags=[],
        error=None,
    )
    human_failure = SimpleNamespace(
        run_id="run-no-correction",
        key="thumbs",
        score=False,
        value=False,
        correction=None,
        feedback_source={"type": "api"},
    )

    class Client:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def list_runs(self, **_kwargs: Any):
            return iter([run])

        def list_feedback(self, **_kwargs: Any):
            return iter([human_failure])

    fake_langsmith = ModuleType("langsmith")
    fake_langsmith.Client = Client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langsmith", fake_langsmith)
    monkeypatch.setattr(langsmith_adapter, "validate_runtime_llm_api_base", lambda endpoint: endpoint)
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.LANGSMITH_API_KEY,
        secret="vault-langsmith-secret",
    )

    cases = langsmith_adapter.LangSmithAdapter(
        credential_id=credential_id,
        credential_vault=vault,
    ).import_annotated_failures("reviewed-project")

    assert len(cases) == 1
    assert cases[0].expected.answer is not None
    assert cases[0].expected.answer.must_be_grounded is True
