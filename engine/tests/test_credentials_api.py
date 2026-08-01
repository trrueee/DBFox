from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status
from sqlalchemy.orm import sessionmaker

from engine.api.credentials import (
    api_release_credential_lease,
    enroll_credential,
    enroll_credentials,
    router,
)
from engine.errors import DBFoxError
from engine.models import CredentialLeaseRecord
from engine.schemas.credentials import CredentialEnrollmentBatchRequest, CredentialEnrollmentRequest
from engine.security.credential_lease import CredentialLeaseSaga, CredentialLeaseStatus
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault


def test_enrollment_returns_only_an_opaque_credential_reference(monkeypatch) -> None:
    sentinel = "TEST_LLM_SECRET"
    vault = InMemoryCredentialVault()
    monkeypatch.setattr("engine.api.credentials.get_credential_vault", lambda: vault)

    reference = enroll_credential(
        CredentialEnrollmentRequest(kind=CredentialKind.LLM_API_KEY, secret=sentinel)
    )

    serialized = reference.model_dump_json()
    assert reference.id.startswith("cred_llm_api_key_")
    assert reference.kind is CredentialKind.LLM_API_KEY
    assert sentinel not in serialized


def test_batch_enrollment_removes_partially_created_credentials_on_failure(db_session) -> None:
    class FailingSecondWriteVault(InMemoryCredentialVault):
        def put(
            self,
            *,
            kind: CredentialKind,
            secret: str,
            credential_id: str | None = None,
        ) -> str:
            if kind is CredentialKind.SSH_PASSWORD:
                raise RuntimeError("write-sentinel")
            return super().put(
                kind=kind,
                secret=secret,
                credential_id=credential_id,
            )

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
        enroll_credentials(request, db=db_session, vault=vault)

    assert vault._credentials == {}
    lease = db_session.query(CredentialLeaseRecord).one()
    assert lease.status == CredentialLeaseStatus.RELEASED.value


def test_batch_enrollment_returns_a_server_owned_lease_for_every_reference(db_session) -> None:
    vault = InMemoryCredentialVault()
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

    enrollment = enroll_credentials(request, db=db_session, vault=vault)

    assert enrollment.lease_id.startswith("lease_")
    assert {reference.id for reference in enrollment.credentials} == CredentialLeaseSaga(
        db_session,
        vault,
    ).claim(
        enrollment.lease_id,
        {reference.id for reference in enrollment.credentials},
    )


def test_release_endpoint_deletes_only_its_server_issued_lease_credentials(
    db_session,
    monkeypatch,
) -> None:
    vault = InMemoryCredentialVault()
    monkeypatch.setattr("engine.api.credentials.get_credential_vault", lambda: vault)
    leased_id = vault.put(kind=CredentialKind.LLM_API_KEY, secret="draft-only-secret")
    persistent_id = vault.put(kind=CredentialKind.LLM_API_KEY, secret="saved-secret")
    lease_id = CredentialLeaseSaga(db_session, vault).issue({leased_id})
    db_session.commit()

    response = api_release_credential_lease(lease_id, db_session)

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
    lease = db_session.get(CredentialLeaseRecord, lease_id)
    assert lease is not None and lease.status == CredentialLeaseStatus.RELEASED.value


def test_reconcile_commits_claimed_lease_when_datasource_owns_reference(
    db_session,
    test_datasource,
) -> None:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="database-secret",
    )
    saga = CredentialLeaseSaga(db_session, vault)
    lease_id = saga.issue({credential_id})
    db_session.commit()
    saga.claim(lease_id, {credential_id})
    test_datasource.password_credential_id = credential_id
    db_session.commit()

    saga.reconcile()

    lease = db_session.get(CredentialLeaseRecord, lease_id)
    assert lease is not None and lease.status == CredentialLeaseStatus.COMMITTED.value
    assert vault.get(credential_id) == "database-secret"


def test_reconcile_releases_unowned_claim_after_interrupted_operation(db_session) -> None:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="temporary-secret",
    )
    saga = CredentialLeaseSaga(db_session, vault)
    lease_id = saga.issue({credential_id})
    db_session.commit()
    saga.claim(lease_id, {credential_id})
    db_session.commit()

    saga.reconcile()

    lease = db_session.get(CredentialLeaseRecord, lease_id)
    assert lease is not None and lease.status == CredentialLeaseStatus.RELEASED.value
    assert vault.get(credential_id) is None


def test_reconcile_releases_expired_pending_lease_after_process_restart(db_session) -> None:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="expired-secret",
    )
    lease_id = CredentialLeaseSaga(db_session, vault).issue(
        {credential_id},
        ttl_seconds=1,
    )
    db_session.commit()

    SessionLocal = sessionmaker(bind=db_session.get_bind())
    with SessionLocal() as restarted_session:
        CredentialLeaseSaga(restarted_session, vault).reconcile(
            now=datetime.now(UTC) + timedelta(seconds=2)
        )

    db_session.expire_all()
    lease = db_session.get(CredentialLeaseRecord, lease_id)
    assert lease is not None and lease.status == CredentialLeaseStatus.RELEASED.value
    assert vault.get(credential_id) is None


def test_cleanup_pending_retries_when_vault_recovers(db_session, monkeypatch) -> None:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="retry-secret",
    )
    saga = CredentialLeaseSaga(db_session)
    lease_id = saga.issue({credential_id})
    db_session.commit()

    def unavailable_vault():
        raise RuntimeError("vault unavailable")

    monkeypatch.setattr("engine.security.credential_lease.get_credential_vault", unavailable_vault)

    assert saga.release(lease_id) is False
    lease = db_session.get(CredentialLeaseRecord, lease_id)
    assert lease is not None and lease.status == CredentialLeaseStatus.CLEANUP_PENDING.value

    CredentialLeaseSaga(db_session, vault).reconcile()

    db_session.expire_all()
    lease = db_session.get(CredentialLeaseRecord, lease_id)
    assert lease is not None and lease.status == CredentialLeaseStatus.RELEASED.value
    assert vault.get(credential_id) is None


def test_partial_vault_cleanup_is_idempotently_retried(db_session) -> None:
    class FailOnceVault(InMemoryCredentialVault):
        def __init__(self, failing_id: str) -> None:
            super().__init__()
            self.failing_id = failing_id
            self.failed = False

        def delete(self, credential_id: str) -> None:
            if credential_id == self.failing_id and not self.failed:
                self.failed = True
                raise RuntimeError("delete failed once")
            super().delete(credential_id)

    first_id = "cred_datasource_password_first"
    second_id = "cred_ssh_password_second"
    vault = FailOnceVault(second_id)
    vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        credential_id=first_id,
        secret="first-secret",
    )
    vault.put(
        kind=CredentialKind.SSH_PASSWORD,
        credential_id=second_id,
        secret="second-secret",
    )
    saga = CredentialLeaseSaga(db_session, vault)
    lease_id = saga.issue({first_id, second_id})
    db_session.commit()

    assert saga.release(lease_id) is False
    assert db_session.get(CredentialLeaseRecord, lease_id).status == (
        CredentialLeaseStatus.CLEANUP_PENDING.value
    )

    saga.reconcile()

    assert db_session.get(CredentialLeaseRecord, lease_id).status == (
        CredentialLeaseStatus.RELEASED.value
    )
    assert vault.get(first_id) is None
    assert vault.get(second_id) is None


def test_committed_lease_cannot_be_released(db_session) -> None:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="committed-secret",
    )
    saga = CredentialLeaseSaga(db_session, vault)
    lease_id = saga.issue({credential_id})
    db_session.commit()
    saga.claim(lease_id, {credential_id})
    saga.commit_claim(lease_id)
    db_session.commit()

    with pytest.raises(DBFoxError) as exc_info:
        saga.release(lease_id)

    assert exc_info.value.code == "CREDENTIAL_LEASE_INVALID"
    assert vault.get(credential_id) == "committed-secret"


@pytest.mark.parametrize(
    "credential_ids,now_offset",
    [
        ({"cred_datasource_password_other"}, 0),
        ({"cred_datasource_password_owned"}, 2),
    ],
)
def test_claim_rejects_wrong_or_expired_ownership(
    db_session,
    credential_ids: set[str],
    now_offset: int,
) -> None:
    owned_id = "cred_datasource_password_owned"
    saga = CredentialLeaseSaga(db_session, InMemoryCredentialVault())
    lease_id = saga.issue({owned_id}, ttl_seconds=1)
    db_session.commit()
    if now_offset:
        lease = db_session.get(CredentialLeaseRecord, lease_id)
        lease.expires_at = datetime.now(UTC) - timedelta(seconds=now_offset)
        db_session.commit()

    with pytest.raises(DBFoxError) as exc_info:
        saga.claim(lease_id, credential_ids)

    assert exc_info.value.code == "CREDENTIAL_LEASE_INVALID"
