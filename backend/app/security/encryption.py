"""Fernet-based symmetric encryption for credential storage at rest.

Usage:
    from app.security.encryption import cipher
    encrypted = cipher.encrypt("sk-abc123...")
    plaintext = cipher.decrypt(encrypted)

The encryption key is loaded from CREDENTIAL_ENCRYPTION_KEY in .env.
On first run without a key, generate one with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("qorvexis.security.encryption")

_SENTINEL = "__UNENCRYPTED__"


class CredentialCipher:
    """Thin wrapper around Fernet for encrypting API keys at rest."""

    def __init__(self) -> None:
        self._fernet: Fernet | None = None

    def _get_fernet(self) -> Fernet:
        if self._fernet is not None:
            return self._fernet

        raw_key = os.environ.get("CREDENTIAL_ENCRYPTION_KEY", "")
        if not raw_key:
            # Attempt to read from settings (imported lazily to avoid circular)
            try:
                from app.settings import settings
                raw_key = getattr(settings, "credential_encryption_key", "") or ""
            except Exception:
                pass

        if not raw_key:
            raise RuntimeError(
                "CREDENTIAL_ENCRYPTION_KEY is not set. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )

        try:
            self._fernet = Fernet(raw_key.encode() if isinstance(raw_key, str) else raw_key)
            logger.info("security.encryption.initialized")
            return self._fernet
        except Exception as exc:
            raise RuntimeError(f"Invalid CREDENTIAL_ENCRYPTION_KEY: {exc}") from exc

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string and return a base64-encoded ciphertext."""
        if not plaintext:
            return plaintext
        f = self._get_fernet()
        return f.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a Fernet ciphertext. Raises ValueError on tamper/key mismatch."""
        if not ciphertext:
            return ciphertext
        # Gracefully handle legacy plaintext rows (migration safety net)
        if not ciphertext.startswith("gAAAA"):
            logger.warning("security.encryption.legacy_plaintext_detected — returning as-is")
            return ciphertext
        f = self._get_fernet()
        try:
            return f.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            logger.error("security.encryption.decrypt_failed — invalid token or wrong key")
            raise ValueError("Credential decryption failed. Key mismatch or data corruption.") from exc

    def is_available(self) -> bool:
        """Return True if a valid key is configured."""
        try:
            self._get_fernet()
            return True
        except Exception:
            return False


cipher = CredentialCipher()
