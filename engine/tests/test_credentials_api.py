from __future__ import annotations

import pytest
from fastapi import status

from engine.api.credentials import (
    CredentialLeaseRegistry,
    api_release_credential_lease,
    enroll_credential,
    enroll_credentials,
    router,
)
from engine.schemas.credentials import CredentialEnrollmentBatchRequest, CredentialEnrollmentRequest
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


def test_batch_enrollment_removes_partially_created_credentials_on_failure() -> None:
    class FailingSecondWriteVault(InMemoryCredentialVault):
        def put(self, *, kind: CredentialKind, secret: str) -> str:
            if kind is CredentialKind.SSH_PASSWORD:
                raise RuntimeError("write-sentinel")
            return super().put(kind=kind, secret=secret)

    vault = FailingSecondWriteVault()
    request = CredentialEnrollmentBatchRequest(
        credentials=[
            CredentialEnrollmentRequest(
                kind=CredentialKind.DATASOURCE_PASSWORD,
                secret="database-secret",
            ),
            CredentialEnrollmentRequest(
                kind=CredentialKind.SSH_PASSWORD,
                secret="ssh-secret",
            ),
        ]
    )

    with pytest.raises(RuntimeError, match="write-sentinel"):
        enroll_credentials(request, vault=vault)

    assert vault._credentials == {}


def test_batch_enrollment_returns_a_server_owned_lease_for_every_reference() -> None:
    vault = InMemoryCredentialVault()
    leases = CredentialLeaseRegistry()
    request = CredentialEnrollmentBatchRequest(
        credentials=[
            CredentialEnrollmentRequest(
                kind=CredentialKind.DATASOURCE_PASSWORD,
                secret="database-secret",
            ),
            CredentialEnrollmentRequest(
                kind=CredentialKind.SSH_PASSWORD,
                secret="ssh-secret",
            ),
        ]
    )

    enrollment = enroll_credentials(request, vault=vault, leases=leases)

    assert enrollment.lease_id.startswith("lease_")
    assert {reference.id for reference in enrollment.credentials} == leases.claim(
        enrollment.lease_id,
        {reference.id for reference in enrollment.credentials},
    )


def test_release_endpoint_deletes_only_its_server_issued_lease_credentials(monkeypatch) -> None:
    vault = InMemoryCredentialVault()
    leases = CredentialLeaseRegistry()
    monkeypatch.setattr("engine.api.credentials.get_credential_vault", lambda: vault)
    monkeypatch.setattr("engine.api.credentials.get_credential_lease_registry", lambda: leases)
    leased_id = vault.put(kind=CredentialKind.LLM_API_KEY, secret="draft-only-secret")
    persistent_id = vault.put(kind=CredentialKind.LLM_API_KEY, secret="saved-secret")
    lease_id = leases.issue({leased_id})

    response = api_release_credential_lease(lease_id)

    route = next(
        route
        for route in router.routes
        if route.path == "/credentials/leases/{lease_id}" and "DELETE" in route.methods
    )
    assert route.status_code == status.HTTP_204_NO_CONTENT
    assert route.response_model is None
    assert response is None
    assert vault.get(leased_id) is None
    assert vault.get(persistent_id) == "saved-secret"
