import logging
from sqlalchemy.orm import Session
from app.gateway.provider_credentials.provider_credentials import ProviderCredential

logger = logging.getLogger("qorvexis.gateway.credentials")

class CredentialManager:
    """Manages API Keys securely for the AI Gateway."""

    def add_credential(self, db: Session, provider: str, api_key: str) -> ProviderCredential:
        # In a real production system, encrypt this using KMS or a local secret key.
        # For Qorvexis phase 10B, we simulate secure storage by retaining the raw string (encrypted_key column)
        # but only ever exposing the masked key in logs/UI.
        
        masked = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "****"
        
        # Deactivate older keys for this provider to keep it simple, or allow multiple active keys.
        # We will deactivate older keys so there's exactly one active key per provider.
        older_keys = db.query(ProviderCredential).filter(
            ProviderCredential.provider == provider,
            ProviderCredential.is_active == True
        ).all()
        for k in older_keys:
            k.is_active = False
            
        cred = ProviderCredential(
            provider=provider,
            encrypted_key=api_key, # Pseudo-encryption
            masked_key=masked,
            is_active=True
        )
        db.add(cred)
        db.commit()
        db.refresh(cred)
        logger.info("gateway.credentials.added provider=%s id=%s masked=%s", provider, cred.id, masked)
        return cred

    def get_active_credential(self, db: Session, provider: str) -> str | None:
        """Retrieves the plaintext API key for the gateway to use."""
        cred = db.query(ProviderCredential).filter(
            ProviderCredential.provider == provider,
            ProviderCredential.is_active == True
        ).first()
        if cred:
            return cred.encrypted_key # In production, this would be decrypted
        return None

    def list_credentials(self, db: Session) -> list[dict]:
        creds = db.query(ProviderCredential).order_by(ProviderCredential.created_at.desc()).all()
        return [
            {
                "id": c.id,
                "provider": c.provider,
                "masked_key": c.masked_key,
                "is_active": c.is_active,
                "created_at": c.created_at.isoformat()
            }
            for c in creds
        ]

credential_manager = CredentialManager()
