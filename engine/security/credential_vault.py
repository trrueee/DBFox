from __future__ import annotations

from enum import StrEnum
import sys
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


_OS_NATIVE_KEYRING_BACKENDS: dict[str, frozenset[tuple[str, str]]] = {
    "win32": frozenset({("keyring.backends.Windows", "WinVaultKeyring")}),
    "darwin": frozenset({("keyring.backends.macOS", "Keyring")}),
    "linux": frozenset(
        {
            ("keyring.backends.SecretService", "Keyring"),
            ("keyring.backends.kwallet", "DBusKeyring"),
        }
    ),
}


def _require_os_native_keyring_backend() -> None:
    """Fail closed unless keyring selected a known OS-native secure backend."""
    try:
        backend = keyring.get_keyring()
    except Exception as exc:
        raise CredentialVaultUnavailableError() from exc

    backend_type = type(backend)
    allowed_backends = _OS_NATIVE_KEYRING_BACKENDS.get(sys.platform, frozenset())
    backend_identity = (backend_type.__module__, backend_type.__name__)
    if backend_identity not in allowed_backends:
        raise CredentialVaultUnavailableError()


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
        value = _normalized_secret(secret)
        credential_id = _credential_id(kind)
        _require_os_native_keyring_backend()
        try:
            keyring.set_password(self.service_name, credential_id, value)
        except Exception as exc:
            raise CredentialVaultUnavailableError() from exc
        return credential_id

    def get(
        self,
        credential_id: str,
        *,
        expected_kind: CredentialKind | None = None,
    ) -> str | None:
        _require_os_native_keyring_backend()
        if not _matches_expected_kind(credential_id, expected_kind):
            return None
        try:
            return keyring.get_password(self.service_name, credential_id)
        except Exception as exc:
            raise CredentialVaultUnavailableError() from exc

    def delete(self, credential_id: str) -> None:
        _require_os_native_keyring_backend()
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
