from __future__ import annotations

import pytest

from engine.security.credential_vault import CredentialKind


def test_qwen_baseline_resolves_its_key_only_from_an_llm_credential_reference(
    monkeypatch,
) -> None:
    from engine.evaluation.spider import spider_eval

    captured: dict[str, object] = {}

    class Vault:
        def get(
            self,
            credential_id: str,
            *,
            expected_kind: CredentialKind | None = None,
        ) -> str:
            captured["credential_id"] = credential_id
            captured["expected_kind"] = expected_kind
            return "TEST_LLM_SECRET"

    monkeypatch.setattr(spider_eval, "get_credential_vault", lambda: Vault())

    assert (
        spider_eval._resolve_qwen_baseline_api_key("cred_llm_api_key_eval")
        == "TEST_LLM_SECRET"
    )
    assert captured == {
        "credential_id": "cred_llm_api_key_eval",
        "expected_kind": CredentialKind.LLM_API_KEY,
    }


def test_qwen_baseline_rejects_missing_or_unavailable_credential_reference(
    monkeypatch,
) -> None:
    from engine.evaluation.spider import spider_eval

    class EmptyVault:
        def get(self, *_args, **_kwargs) -> None:
            return None

    monkeypatch.setattr(spider_eval, "get_credential_vault", lambda: EmptyVault())

    with pytest.raises(RuntimeError, match="--llm-credential-id"):
        spider_eval._resolve_qwen_baseline_api_key(None)
    with pytest.raises(RuntimeError, match="unavailable"):
        spider_eval._resolve_qwen_baseline_api_key("cred_llm_api_key_missing")
