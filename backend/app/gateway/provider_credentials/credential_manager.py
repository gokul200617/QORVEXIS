"""Credential Manager — Phase 10D.

All API keys are encrypted with Fernet before persistence.
Plaintext keys are NEVER logged, returned to clients, or stored in cleartext.
"""

import logging
from sqlalchemy.orm import Session

from app.gateway.provider_credentials.provider_credentials import ProviderCredential
from app.security.encryption import cipher

logger = logging.getLogger("qorvexis.gateway.credentials")


class CredentialManager:
    """Manages encrypted API Keys for the AI Gateway."""

    def add_credential(
        self,
        db: Session,
        provider: str,
        api_key: str,
        org_id: str | None = None,
    ) -> ProviderCredential:
        if not api_key or not api_key.strip():
            raise ValueError("API key must not be empty.")

        masked = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "****"

        # Deactivate older keys for same provider + org
        older_keys = db.query(ProviderCredential).filter(
            ProviderCredential.provider == provider,
            ProviderCredential.is_active == True,
            ProviderCredential.organization_id == org_id,
        ).all()
        for k in older_keys:
            k.is_active = False

        # Encrypt before persistence — plaintext never hits the DB
        encrypted = cipher.encrypt(api_key)

        cred = ProviderCredential(
            organization_id=org_id,
            provider=provider,
            encrypted_key=encrypted,
            masked_key=masked,
            is_active=True,
        )
        db.add(cred)
        db.commit()
        db.refresh(cred)
        # NEVER log the raw key or the masked variant exposes provider
        logger.info(
            "gateway.credentials.added provider=%s id=%s org=%s",
            provider, cred.id, org_id,
        )
        return cred

    def get_active_credential(
        self, db: Session, provider: str, org_id: str | None = None
    ) -> str | None:
        """Return the decrypted API key for in-memory gateway use only."""
        filters = [
            ProviderCredential.provider == provider,
            ProviderCredential.is_active == True,
        ]
        if org_id:
            filters.append(ProviderCredential.organization_id == org_id)

        cred = db.query(ProviderCredential).filter(*filters).first()
        if not cred:
            return None

        try:
            return cipher.decrypt(cred.encrypted_key)
        except ValueError:
            logger.error(
                "gateway.credentials.decrypt_failed provider=%s id=%s",
                provider, cred.id,
            )
            return None

    def list_credentials(self, db: Session, org_id: str | None = None) -> list[dict]:
        """Return masked credential metadata — never the decrypted key."""
        q = db.query(ProviderCredential)
        if org_id:
            q = q.filter(ProviderCredential.organization_id == org_id)
        creds = q.order_by(ProviderCredential.created_at.desc()).all()
        return [
            {
                "id": c.id,
                "provider": c.provider,
                "masked_key": c.masked_key,  # safe to return
                "is_active": c.is_active,
                "created_at": c.created_at.isoformat(),
            }
            for c in creds
        ]

    def revoke_credential(self, db: Session, credential_id: str, org_id: str | None = None) -> bool:
        """Deactivate a credential by ID. Returns True if found."""
        q = db.query(ProviderCredential).filter(ProviderCredential.id == credential_id)
        if org_id:
            q = q.filter(ProviderCredential.organization_id == org_id)
        cred = q.first()
        if not cred:
            return False
        cred.is_active = False
        db.commit()
        logger.info("gateway.credentials.revoked id=%s org=%s", credential_id, org_id)
        return True


credential_manager = CredentialManager()
