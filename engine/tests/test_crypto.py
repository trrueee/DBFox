"""Tests for crypto module — encrypt/decrypt password flow."""
import pytest
from engine import crypto
from engine.crypto import encrypt_password, decrypt_password, get_or_create_key


def test_encrypt_returns_tuple() -> None:
    cipher, nonce = encrypt_password("mypassword")
    assert isinstance(cipher, str)
    assert isinstance(nonce, str)
    assert len(cipher) > 0
    assert len(nonce) > 0


def test_decrypt_restores_original() -> None:
    original = "MySecureP@ssw0rd!"
    cipher, nonce = encrypt_password(original)
    decrypted = decrypt_password(cipher, nonce)
    assert decrypted == original


def test_encrypt_empty_password() -> None:
    cipher, nonce = encrypt_password("")
    assert cipher == ""
    assert nonce == ""


def test_decrypt_empty_credentials() -> None:
    assert decrypt_password("", "") == ""


def test_encrypt_different_passwords_have_different_ciphertexts() -> None:
    c1, n1 = encrypt_password("password1")
    c2, n2 = encrypt_password("password2")
    assert c1 != c2


def test_encrypt_same_password_has_different_ciphertext() -> None:
    """Each encryption should produce unique nonce+ciphertext pair."""
    c1, n1 = encrypt_password("same_password")
    c2, n2 = encrypt_password("same_password")
    assert (c1, n1) != (c2, n2), "AES-GCM should produce unique nonces per encryption"


def test_decrypt_with_wrong_ciphertext_raises() -> None:
    with pytest.raises(ValueError, match="Failed to decrypt"):
        decrypt_password("invalid_base64!!", "invalid_nonce!!")


def test_decrypt_with_wrong_nonce_raises() -> None:
    _, n1 = encrypt_password("password1")
    c2, _ = encrypt_password("password2")
    with pytest.raises(ValueError, match="Failed to decrypt"):
        decrypt_password(c2, n1)


def test_unicode_password() -> None:
    original = "密码测试!@#$%^&*()_+-=[]{}|;':,.<>?/~`"
    cipher, nonce = encrypt_password(original)
    assert decrypt_password(cipher, nonce) == original


def test_long_password() -> None:
    original = "A" * 1000
    cipher, nonce = encrypt_password(original)
    assert decrypt_password(cipher, nonce) == original


def test_key_persistence() -> None:
    """Verify get_or_create_key returns the same key on subsequent calls."""
    key1 = get_or_create_key()
    key2 = get_or_create_key()
    assert key1 == key2
    assert len(key1) == 32  # 256-bit key


def test_key_file_not_stored_in_engine_directory() -> None:
    """New key material should live outside the importable engine package."""
    from pathlib import Path
    engine_dir = Path(__file__).resolve().parent.parent
    assert crypto.KEY_FILE.parent != engine_dir


def test_keyring_lifecycle_and_migration(monkeypatch) -> None:
    """Verify that get_or_create_key correctly saves/loads from a mocked keyring database."""
    import sys
    import base64
    
    # 1. Create a dynamic mock keyring store
    keyring_store = {}
    
    class MockKeyring:
        @staticmethod
        def get_password(service: str, username: str) -> str | None:
            return keyring_store.get((service, username))
            
        @staticmethod
        def set_password(service: str, username: str, password: str) -> None:
            keyring_store[(service, username)] = password

    # 2. Inject mock keyring module
    monkeypatch.setitem(sys.modules, "keyring", MockKeyring)
    
    # 3. Force recalculation of key using mocked keyring service names
    # Temporary patch service names to prevent collision with actual workspace keys
    monkeypatch.setattr(crypto, "KEYRING_SERVICE", "DBFoxTestService")
    monkeypatch.setattr(crypto, "KEYRING_USERNAME", "DBFoxTestUser")
    
    # 4. Generate key and verify persistence inside mocked OS Keychain
    key = get_or_create_key()
    assert len(key) == 32
    
    # Ensure key was written to mock keyring
    stored_b64 = keyring_store.get(("DBFoxTestService", "DBFoxTestUser"))
    assert stored_b64 is not None
    
    # Ensure decrypted base64 matches original generated key bytes
    decoded = base64.b64decode(stored_b64.encode("utf-8"))
    assert decoded == key
    
    # 5. Subsequent calls should load from mock keyring directly
    key2 = get_or_create_key()
    assert key2 == key
