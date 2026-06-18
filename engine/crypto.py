import base64
import os
import logging
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from engine.runtime_paths import private_runtime_file, write_private_bytes, _chmod_private

logger = logging.getLogger("dbfox.crypto")

KEY_FILE = private_runtime_file("secrets", ".secret_key")

KEYRING_SERVICE = "DBFox"
KEYRING_USERNAME = "DatabaseClientSecretKey"


def get_or_create_key() -> bytes:
    """Return the current symmetric encryption key, creating one if necessary.

    Priority order (file is authoritative; keyring is a best-effort cache):

    1. **Private runtime file** — the canonical key store. Always consulted
       first so that the key survives keyring outages.
    2. **OS keyring** — if no file key exists, try the keyring and
       **mirror** any key found there into the file.  This handles
       upgrades from older versions that only wrote to the keyring.
    3. **Generate** a fresh AES-256 key, persist it to the file
       (authoritative), then attempt to cache it in the keyring.

    This ordering prevents the "split-brain" scenario where keyring
    intermittent availability causes two different keys to exist in the
    two stores, making previously encrypted data unrecoverable.
    """
    # 1. Primary / authoritative: private runtime file
    if KEY_FILE.exists():
        try:
            key = KEY_FILE.read_bytes()
            _chmod_private(KEY_FILE, is_dir=False)
            # Best-effort: ensure the keyring has a copy for backwards compat
            _mirror_to_keyring(key)
            return key
        except Exception as e:
            logger.critical(
                "Key file exists but failed to read: %s. Aborting.", e
            )
            raise RuntimeError(
                f"Could not read existing secret key file: {e}"
            ) from e

    # 2. Fallback: try the OS keyring (handles upgrades from keyring-only era)
    keyring_key = _load_from_keyring()
    if keyring_key is not None:
        logger.info("Retrieved existing key from OS keyring; mirroring to file.")
        _persist_key_file(keyring_key)
        _mirror_to_keyring(keyring_key)
        return keyring_key

    # 3. No key exists anywhere — generate a new one
    new_key = AESGCM.generate_key(bit_length=256)  # type: ignore[call-arg]

    # File is authoritative — must succeed before we consider the key usable
    try:
        _persist_key_file(new_key)
    except Exception as e:
        logger.critical("Failed to persist newly generated secret key: %s", e)
        raise RuntimeError(
            "Could not write secret key file — refusing to operate with an "
            "unpersisted key."
        ) from e

    # Keyring is a best-effort cache
    _mirror_to_keyring(new_key)
    logger.info("Generated and persisted a new symmetric encryption key.")
    return new_key


def _load_from_keyring() -> bytes | None:
    """Try to read the symmetric key from the OS keyring.

    Returns ``None`` when the keyring is unavailable or holds no key.
    """
    try:
        import keyring
        stored_b64 = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        if stored_b64:
            try:
                return base64.b64decode(stored_b64.encode("utf-8"))
            except Exception:
                logger.warning(
                    "OS keyring secret key corrupted; ignoring keyring copy."
                )
    except Exception as e:
        logger.debug("OS keyring unavailable: %s", e)
    return None


def _mirror_to_keyring(key: bytes) -> None:
    """Best-effort cache of *key* in the OS keyring for backwards compatibility."""
    try:
        import keyring
        b64_key = base64.b64encode(key).decode("utf-8")
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, b64_key)
    except Exception as e:
        logger.debug("Failed to mirror key to OS keyring: %s", e)


def _persist_key_file(key: bytes) -> None:
    """Write *key* to the private runtime key file with restricted permissions."""
    write_private_bytes(KEY_FILE, key)
    _chmod_private(KEY_FILE, is_dir=False)


def encrypt_password(password: str) -> tuple[str, str]:
    """Encrypts a database password using AES-256-GCM.

    Returns (ciphertext_b64, nonce_b64).
    """
    if not password:
        return "", ""
    key = get_or_create_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    data = password.encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, data, None)

    ciphertext_b64 = base64.b64encode(ciphertext).decode("utf-8")
    nonce_b64 = base64.b64encode(nonce).decode("utf-8")
    return ciphertext_b64, nonce_b64


def decrypt_password(ciphertext_b64: str, nonce_b64: str) -> str:
    """Decrypts an AES-256-GCM encrypted database password.

    Returns the plain password.
    """
    if not ciphertext_b64 or not nonce_b64:
        return ""
    key = get_or_create_key()
    aesgcm = AESGCM(key)
    try:
        ciphertext = base64.b64decode(ciphertext_b64.encode("utf-8"))
        nonce = base64.b64decode(nonce_b64.encode("utf-8"))
        data = aesgcm.decrypt(nonce, ciphertext, None)
        return data.decode("utf-8")
    except Exception as exc:
        logger.exception("Failed to decrypt database credentials")
        raise ValueError("Failed to decrypt database credentials") from exc
