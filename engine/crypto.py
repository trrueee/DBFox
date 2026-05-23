import base64
import os
import sys
import logging
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from engine.runtime_paths import private_runtime_file, write_private_bytes

logger = logging.getLogger("databox.crypto")

ENGINE_DIR = Path(__file__).resolve().parent
LEGACY_KEY_FILE = ENGINE_DIR / ".secret_key"
KEY_FILE = private_runtime_file("secrets", ".secret_key")

KEYRING_SERVICE = "DataBox"
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

    # 2. Secondary: Fallback & Migration of legacy file key
    legacy_key = None
    if not KEY_FILE.exists() and LEGACY_KEY_FILE.exists():
        try:
            write_private_bytes(KEY_FILE, LEGACY_KEY_FILE.read_bytes())
        except Exception:
            pass

    if KEY_FILE.exists():
        try:
            legacy_key = KEY_FILE.read_bytes()
        except Exception:
            pass

    # 3. If we have a legacy file key, migrate it into the OS Keychain and prune the file
    if legacy_key is not None:
        try:
            import keyring
            b64_key = base64.b64encode(legacy_key).decode("utf-8")
            keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, b64_key)
            try:
                KEY_FILE.unlink(missing_ok=True)
                LEGACY_KEY_FILE.unlink(missing_ok=True)
                logger.info("Successfully migrated symmetric key to OS Keychain and removed local files.")
            except Exception:
                pass
            return legacy_key
        except Exception as e:
            logger.warning(f"Failed to migrate legacy key to OS Keychain: {e}")
            return legacy_key

    # 4. Generate new symmetric key if none exists
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

    # 5. File system fallback if keychain is completely unavailable
    try:
        write_private_bytes(KEY_FILE, new_key)
        logger.info("Symmetric key stored in local file system fallback.")
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
    except Exception:
        raise ValueError("Failed to decrypt database credentials") from None
