"""ConnectorCredentialMetadata — safe metadata about connector auth config.

IMPORTANT: This model stores ONLY metadata about the authentication
configuration — NOT raw secrets, API keys, or tokens.

Secret material must be stored in an external vault (e.g. AWS Secrets
Manager, HashiCorp Vault) and referenced by a safe_reference_key only.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class ConnectorCredentialMetadata(Base):
    """Safe metadata record describing how a connector authenticates.

    Fields:
        auth_type        : e.g. 'api_key', 'oauth2', 'iam_role'
        safe_reference   : opaque vault reference key (not the secret itself)
        masked_identifier: masked preview of the identifier (e.g. 'sk-...xxxx')
    """

    __tablename__ = "connector_credential_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    connector_id:      Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    auth_type:         Mapped[str] = mapped_column(String(64),  nullable=False)
    safe_reference:    Mapped[str | None] = mapped_column(String(256), nullable=True)
    masked_identifier: Mapped[str | None] = mapped_column(String(64),  nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
