"""Credential enrollment contracts.

Secrets appear only in :class:`CredentialEnrollmentRequest` while an HTTP
request is being handled.  Every persisted or returned value is a
``CredentialReference`` instead.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from engine.security.credential_vault import CredentialKind


class CredentialReference(BaseModel):
    """Opaque reference to a secret stored by the operating-system keyring."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=256)
    kind: CredentialKind


class CredentialEnrollmentRequest(BaseModel):
    """Transient enrollment input; never persist or return this model."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: CredentialKind
    secret: SecretStr = Field(min_length=1, max_length=4096)
