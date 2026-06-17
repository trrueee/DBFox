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
    # 1. Primary: Try loading symmetric key from OS Keychain
    keyring_key = None
    try:
        import keyring
        stored_b64 = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        if stored_b64:
            try:
                keyring_key = base64.b64decode(stored_b64.encode("utf-8"))
            except Exception:
                logger.warning("OS Keychain secret key corrupted; regenerating key.")
    except Exception as e:
        logger.warning(f"OS Keychain via keyring is unavailable: {e}")

    if keyring_key is not None:
        return keyring_key

    # 2. Fallback: read key from private runtime file
    if KEY_FILE.exists():
        try:
            key = KEY_FILE.read_bytes()
            _chmod_private(KEY_FILE, is_dir=False)
            return key
        except Exception as e:
            logger.critical(f"Key file exists but failed to read: {e}. Aborting to prevent credential loss.")
            raise RuntimeError(f"Could not read existing secret key file: {e}") from e

    # 3. Generate new symmetric key if none exists
    new_key = AESGCM.generate_key(bit_length=256)  # type: ignore[call-arg]
    
    # Try storing it in the OS Keychain
    saved_in_keyring = False
    try:
        import keyring
        b64_key = base64.b64encode(new_key).decode("utf-8")
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, b64_key)
        saved_in_keyring = True
        logger.info("Successfully generated and saved symmetric key in OS Keychain.")
    except Exception as e:
        logger.warning(f"Failed to store generated symmetric key in OS Keychain: {e}")

    if saved_in_keyring:
        return new_key

    # 4. File system fallback if keychain is completely unavailable
    try:
        write_private_bytes(KEY_FILE, new_key)
        _chmod_private(KEY_FILE, is_dir=False)
        logger.warning(
            "OS keychain unavailable; using local encrypted-key fallback. "
            "Restricting key file to current user."
        )
    except Exception as e:
        logger.error(f"Critical: Failed to save fallback symmetric key: {e}")
        
    return new_key


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
