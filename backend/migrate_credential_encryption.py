"""Phase 10D.1 — Credential Re-Encryption Migration.

One-time migration that:
  1. Reads every ProviderCredential row from the database.
  2. Detects whether encrypted_key is already Fernet-encrypted or plaintext.
  3. Encrypts all plaintext values with the configured CREDENTIAL_ENCRYPTION_KEY.
  4. Writes the ciphertext back.
  5. Verifies every row decrypts correctly (round-trip check).
  6. Reports a full audit trail.

Usage:
    # First, set the encryption key in your .env:
    #   CREDENTIAL_ENCRYPTION_KEY=<your-fernet-key>
    # Generate a key if you don't have one:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

    python migrate_credential_encryption.py [--dry-run]

Flags:
    --dry-run   Scan and report without writing any changes.

SAFETY:
    - No credential is deleted — only encrypted_key is updated in-place.
    - Already-encrypted rows are skipped (idempotent).
    - Any failure aborts and rolls back the entire transaction.
    - A verification pass after commit catches any silent corruption.
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("qorvexis.migration.credential_encryption")


def _is_fernet_ciphertext(value: str) -> bool:
    """Fernet tokens always start with 'gAAAA' (base64-encoded 0x80 version byte)."""
    return value.startswith("gAAAA")


def run_migration(dry_run: bool = False) -> None:
    logger.info("=" * 60)
    logger.info("  Phase 10D.1 — Credential Re-Encryption Migration")
    logger.info("  Mode: %s", "DRY-RUN (no writes)" if dry_run else "LIVE (will write to DB)")
    logger.info("=" * 60)

    # ── Validate encryption key ────────────────────────────────────────────────
    # Import settings first so .env is loaded
    from app.settings import settings  # noqa: E402
    from app.security.encryption import cipher  # noqa: E402

    if not settings.credential_encryption_key:
        logger.error(
            "CREDENTIAL_ENCRYPTION_KEY is not set in your .env file.\n"
            "Generate one with:\n"
            "  python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"\n"
            "Then add it to .env as:\n"
            "  CREDENTIAL_ENCRYPTION_KEY=<your-key>"
        )
        sys.exit(1)

    # Validate the key works before touching DB
    try:
        test_round_trip = cipher.decrypt(cipher.encrypt("__key_validation_test__"))
        assert test_round_trip == "__key_validation_test__"
    except Exception as exc:
        logger.error("Encryption key validation FAILED: %s", exc)
        sys.exit(1)

    logger.info("Encryption key: valid")

    # ── Connect to DB ──────────────────────────────────────────────────────────
    from app.database.session import SessionLocal  # noqa: E402
    from app.gateway.provider_credentials.provider_credentials import ProviderCredential  # noqa: E402

    db = SessionLocal()

    try:
        all_creds = db.query(ProviderCredential).order_by(ProviderCredential.created_at).all()
        total = len(all_creds)
        logger.info("Found %d credential row(s) in database.", total)

        if total == 0:
            logger.info("Nothing to migrate. Exiting.")
            return

        already_encrypted = []
        to_encrypt = []

        for cred in all_creds:
            if _is_fernet_ciphertext(cred.encrypted_key):
                already_encrypted.append(cred)
            else:
                to_encrypt.append(cred)

        logger.info(
            "Scan complete: %d already encrypted, %d plaintext (need migration).",
            len(already_encrypted), len(to_encrypt),
        )

        if not to_encrypt:
            logger.info("All credentials are already encrypted. No action needed.")
            return

        # ── Log what will change ───────────────────────────────────────────────
        logger.info("")
        logger.info("Rows to encrypt:")
        for cred in to_encrypt:
            logger.info(
                "  id=%-36s  provider=%-20s  org=%-36s  masked=%s",
                cred.id, cred.provider, cred.organization_id or "none", cred.masked_key,
            )

        if dry_run:
            logger.info("")
            logger.info("DRY-RUN complete — no writes performed.")
            logger.info("Re-run without --dry-run to apply migration.")
            return

        # ── Encrypt and write back ─────────────────────────────────────────────
        logger.info("")
        logger.info("Starting encryption pass...")

        encrypted_this_run: list[tuple[str, str]] = []  # (id, original_plaintext)

        for cred in to_encrypt:
            plaintext = cred.encrypted_key  # currently stored as plaintext
            ciphertext = cipher.encrypt(plaintext)
            cred.encrypted_key = ciphertext
            encrypted_this_run.append((cred.id, plaintext))
            logger.info("  Encrypted id=%s provider=%s", cred.id, cred.provider)

        # Commit all changes atomically
        db.commit()
        logger.info("Commit: %d row(s) written.", len(encrypted_this_run))

        # ── Verification pass ──────────────────────────────────────────────────
        logger.info("")
        logger.info("Running verification pass (decrypt and compare)...")

        verification_failures = []
        db.expire_all()  # Force re-read from DB

        for cred_id, original_plaintext in encrypted_this_run:
            fresh = db.query(ProviderCredential).filter_by(id=cred_id).first()
            if not fresh:
                verification_failures.append((cred_id, "row_not_found_after_commit"))
                continue

            if not _is_fernet_ciphertext(fresh.encrypted_key):
                verification_failures.append((cred_id, "ciphertext_not_written_to_db"))
                continue

            try:
                decrypted = cipher.decrypt(fresh.encrypted_key)
                if decrypted != original_plaintext:
                    verification_failures.append((cred_id, f"decrypt_mismatch: got len={len(decrypted)} expected len={len(original_plaintext)}"))
                else:
                    logger.info("  VERIFIED id=%s", cred_id)
            except Exception as exc:
                verification_failures.append((cred_id, f"decrypt_error: {exc}"))

        # ── Final report ───────────────────────────────────────────────────────
        logger.info("")
        logger.info("=" * 60)
        logger.info("  MIGRATION REPORT")
        logger.info("  Timestamp : %s", datetime.now(timezone.utc).isoformat())
        logger.info("  Total rows: %d", total)
        logger.info("  Skipped   : %d (already encrypted)", len(already_encrypted))
        logger.info("  Migrated  : %d", len(encrypted_this_run))
        logger.info("  Verified  : %d", len(encrypted_this_run) - len(verification_failures))
        logger.info("  Failures  : %d", len(verification_failures))

        if verification_failures:
            logger.error("")
            logger.error("VERIFICATION FAILURES — manual inspection required:")
            for cred_id, reason in verification_failures:
                logger.error("  id=%s  reason=%s", cred_id, reason)
            logger.error("")
            logger.error("STATUS: FAIL")
            sys.exit(2)
        else:
            logger.info("")
            logger.info("STATUS: PASS — all credentials successfully encrypted and verified.")

    except KeyboardInterrupt:
        logger.warning("Migration interrupted by user. Rolling back.")
        db.rollback()
        sys.exit(1)
    except Exception as exc:
        logger.error("Unexpected error during migration: %s", exc)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Phase 10D.1 — Encrypt plaintext credentials at rest using Fernet."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Scan and report without writing any changes to the database.",
    )
    args = parser.parse_args()
    run_migration(dry_run=args.dry_run)
