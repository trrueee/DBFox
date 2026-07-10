from __future__ import annotations

from engine.api.credentials import enroll_credential
from engine.schemas.credentials import CredentialEnrollmentRequest
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault


def test_enrollment_returns_only_an_opaque_credential_reference(monkeypatch) -> None:
    sentinel = "sk-phase1-enrollment-sentinel"
    vault = InMemoryCredentialVault()
    monkeypatch.setattr("engine.api.credentials.get_credential_vault", lambda: vault)

    reference = enroll_credential(
        CredentialEnrollmentRequest(kind=CredentialKind.LLM_API_KEY, secret=sentinel)
    )

    serialized = reference.model_dump_json()
    assert reference.id.startswith("cred_llm_api_key_")
    assert reference.kind is CredentialKind.LLM_API_KEY
    assert sentinel not in serialized
