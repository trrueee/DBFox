"""Local-only credential enrollment routes.

This router deliberately exposes no read operation.  Consumers receive an
opaque reference which can be used by a trusted backend boundary but never a
secret value.
"""
from __future__ import annotations

from fastapi import APIRouter

from engine.schemas.credentials import CredentialEnrollmentRequest, CredentialReference
from engine.security.credential_vault import CredentialVault, get_credential_vault


router = APIRouter()


def enroll_credential(
    request: CredentialEnrollmentRequest,
    *,
    vault: CredentialVault | None = None,
) -> CredentialReference:
    """Store a transient secret and return its opaque keyring reference."""
    credential_vault = vault or get_credential_vault()
    credential_id = credential_vault.put(
        kind=request.kind,
        secret=request.secret.get_secret_value(),
    )
    return CredentialReference(id=credential_id, kind=request.kind)


@router.post("/credentials", response_model=CredentialReference, status_code=201)
def api_enroll_credential(request: CredentialEnrollmentRequest) -> CredentialReference:
    return enroll_credential(request)
