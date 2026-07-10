from __future__ import annotations

import pytest

from engine.errors import DBFoxError
from engine.security.credential_vault import (
    CredentialKind,
    InMemoryCredentialVault,
    KeyringCredentialVault,
)


def test_vault_returns_opaque_id_and_not_the_secret() -> None:
    vault = InMemoryCredentialVault()

    credential_id = vault.put(
        kind=CredentialKind.LLM_API_KEY,
        secret="sk-phase1-sentinel",
    )

    assert credential_id.startswith("cred_")
    assert credential_id != "sk-phase1-sentinel"
    assert vault.get(credential_id) == "sk-phase1-sentinel"


def test_vault_rejects_unknown_or_wrong_kind() -> None:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="db-password",
    )

    assert vault.get(credential_id, expected_kind=CredentialKind.LLM_API_KEY) is None
    assert vault.get("cred_missing") is None


def test_vault_delete_removes_the_opaque_reference() -> None:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.SSH_PASSWORD,
        secret="ssh-phase1-sentinel",
    )

    vault.delete(credential_id)

    assert vault.get(credential_id) is None


def test_keyring_vault_fails_closed_when_keyring_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = KeyringCredentialVault()

    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("keyring unavailable")

    monkeypatch.setattr("engine.security.credential_vault.keyring.set_password", unavailable)

    with pytest.raises(DBFoxError) as exc_info:
        vault.put(kind=CredentialKind.LLM_API_KEY, secret="sk-phase1-sentinel")

    assert exc_info.value.code == "CREDENTIAL_VAULT_UNAVAILABLE"


def test_keyring_reads_fail_closed_when_backend_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = KeyringCredentialVault()

    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("keyring unavailable")

    monkeypatch.setattr("engine.security.credential_vault.keyring.get_password", unavailable)

    with pytest.raises(DBFoxError) as exc_info:
        vault.get("cred_llm_api_key_123", expected_kind=CredentialKind.LLM_API_KEY)

    assert exc_info.value.code == "CREDENTIAL_VAULT_UNAVAILABLE"


def test_keyring_vault_rejects_an_insecure_backend_before_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = KeyringCredentialVault()
    writes: list[tuple[object, ...]] = []

    class InsecureFileBackend:
        pass

    monkeypatch.setattr(
        "engine.security.credential_vault.keyring.get_keyring",
        lambda: InsecureFileBackend(),
    )
    monkeypatch.setattr(
        "engine.security.credential_vault.keyring.set_password",
        lambda *args: writes.append(args),
    )

    with pytest.raises(DBFoxError) as exc_info:
        vault.put(kind=CredentialKind.LLM_API_KEY, secret="sk-phase1-sentinel")

    assert exc_info.value.code == "CREDENTIAL_VAULT_UNAVAILABLE"
    assert writes == []


def test_keyring_vault_rejects_an_insecure_backend_before_any_get(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A kind mismatch must not become a way to probe an insecure backend."""
    vault = KeyringCredentialVault()
    reads: list[tuple[object, ...]] = []

    class InsecureChainerBackend:
        pass

    monkeypatch.setattr(
        "engine.security.credential_vault.keyring.get_keyring",
        lambda: InsecureChainerBackend(),
    )
    monkeypatch.setattr(
        "engine.security.credential_vault.keyring.get_password",
        lambda *args: reads.append(args),
    )

    with pytest.raises(DBFoxError) as exc_info:
        vault.get(
            "cred_datasource_password_123",
            expected_kind=CredentialKind.LLM_API_KEY,
        )

    assert exc_info.value.code == "CREDENTIAL_VAULT_UNAVAILABLE"
    assert reads == []


def test_keyring_vault_rejects_an_insecure_backend_before_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = KeyringCredentialVault()
    deleted: list[tuple[object, ...]] = []

    class InsecurePlaintextBackend:
        pass

    monkeypatch.setattr(
        "engine.security.credential_vault.keyring.get_keyring",
        lambda: InsecurePlaintextBackend(),
    )
    monkeypatch.setattr(
        "engine.security.credential_vault.keyring.delete_password",
        lambda *args: deleted.append(args),
    )

    with pytest.raises(DBFoxError) as exc_info:
        vault.delete("cred_llm_api_key_123")

    assert exc_info.value.code == "CREDENTIAL_VAULT_UNAVAILABLE"
    assert deleted == []


def test_keyring_vault_validates_empty_secret_before_backend_handling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = KeyringCredentialVault()

    monkeypatch.setattr(
        "engine.security.credential_vault.keyring.set_password",
        lambda *_args: pytest.fail("empty secrets must not reach keyring"),
    )

    with pytest.raises(ValueError, match="must not be empty"):
        vault.put(kind=CredentialKind.LLM_API_KEY, secret="  ")


def test_llm_config_resolves_a_secret_only_from_an_opaque_reference() -> None:
    from engine.llm.config import resolve_product_llm_config_from_credential

    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.LLM_API_KEY,
        secret="sk-phase1-llm-sentinel",
    )

    config = resolve_product_llm_config_from_credential(
        llm_credential_id=credential_id,
        api_base="https://example.test/v1",
        model_name="test-model",
        credential_vault=vault,
    )

    assert config.api_key == "sk-phase1-llm-sentinel"
    assert config.api_base == "https://example.test/v1"
    assert config.model_name == "test-model"
