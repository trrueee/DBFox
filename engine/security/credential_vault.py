from __future__ import annotations

from enum import StrEnum
from typing import Protocol
from uuid import uuid4

import keyring

from engine.errors import DBFoxError


class CredentialKind(StrEnum):
    LLM_API_KEY = "llm_api_key"
    LANGSMITH_API_KEY = "langsmith_api_key"
    DATASOURCE_PASSWORD = "datasource_password"
    SSH_PASSWORD = "ssh_password"
    SSH_KEY_PASSPHRASE = "ssh_key_passphrase"


class CredentialVault(Protocol):
    def put(self, *, kind: CredentialKind, secret: str) -> str:
        raise NotImplementedError

    def get(
        self,
        credential_id: str,
        *,
        expected_kind: CredentialKind | None = None,
    ) -> str | None:
        raise NotImplementedError

    def delete(self, credential_id: str) -> None:
        raise NotImplementedError


class CredentialVaultUnavailableError(DBFoxError):
    def __init__(self) -> None:
        super().__init__(
            "Credential vault is unavailable.",
            code="CREDENTIAL_VAULT_UNAVAILABLE",
        )


def _normalized_secret(secret: str) -> str:
    value = secret.strip()
    if not value:
        raise ValueError("Credential secret must not be empty")
    return value


def _credential_id(kind: CredentialKind) -> str:
    return f"cred_{kind.value}_{uuid4().hex}"


def _matches_expected_kind(
    credential_id: str,
    expected_kind: CredentialKind | None,
) -> bool:
    return expected_kind is None or credential_id.startswith(f"cred_{expected_kind.value}_")


class KeyringCredentialVault:
    service_name = "com.dbfox.desktop.credentials"

    def put(self, *, kind: CredentialKind, secret: str) -> str:
        credential_id = _credential_id(kind)
        try:
            keyring.set_password(self.service_name, credential_id, _normalized_secret(secret))
        except Exception as exc:
            raise CredentialVaultUnavailableError() from exc
        return credential_id

    def get(
        self,
        credential_id: str,
        *,
        expected_kind: CredentialKind | None = None,
    ) -> str | None:
        if not _matches_expected_kind(credential_id, expected_kind):
            return None
        try:
            return keyring.get_password(self.service_name, credential_id)
        except Exception as exc:
            raise CredentialVaultUnavailableError() from exc

    def delete(self, credential_id: str) -> None:
        try:
            keyring.delete_password(self.service_name, credential_id)
        except keyring.errors.PasswordDeleteError:
            return
        except Exception as exc:
            raise CredentialVaultUnavailableError() from exc


class InMemoryCredentialVault:
    """Ephemeral fake backend for tests; it never writes a fallback file."""

    def __init__(self) -> None:
        self._credentials: dict[str, tuple[CredentialKind, str]] = {}

    def put(self, *, kind: CredentialKind, secret: str) -> str:
        credential_id = _credential_id(kind)
        self._credentials[credential_id] = (kind, _normalized_secret(secret))
        return credential_id

    def get(
        self,
        credential_id: str,
        *,
        expected_kind: CredentialKind | None = None,
    ) -> str | None:
        credential = self._credentials.get(credential_id)
        if credential is None:
            return None
        kind, secret = credential
        if expected_kind is not None and kind is not expected_kind:
            return None
        return secret

    def delete(self, credential_id: str) -> None:
        self._credentials.pop(credential_id, None)


_application_vault: CredentialVault | None = None


def get_credential_vault() -> CredentialVault:
    global _application_vault
    if _application_vault is None:
        _application_vault = KeyringCredentialVault()
    return _application_vault
