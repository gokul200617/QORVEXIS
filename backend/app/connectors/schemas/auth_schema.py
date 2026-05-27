"""Auth configuration Pydantic schemas.

IMPORTANT: These schemas accept only safe metadata — never raw secrets.
Secret material belongs in a vault, referenced by safe_reference only.
"""

from enum import Enum

from pydantic import BaseModel, Field


class AuthType(str, Enum):
    API_KEY    = "api_key"
    OAUTH2     = "oauth2"
    IAM_ROLE   = "iam_role"
    SERVICE_ACCOUNT = "service_account"
    BASIC_AUTH = "basic_auth"
    NONE       = "none"


class AuthConfigSchema(BaseModel):
    """Safe authentication configuration — no raw secrets."""

    auth_type: AuthType = AuthType.API_KEY

    # Opaque vault reference (e.g. AWS Secrets Manager ARN, Vault path)
    safe_reference: str | None = Field(
        default=None,
        description="Opaque vault reference key. Not the secret itself.",
    )

    # Masked preview (e.g. 'sk-...abcd') for UI display only
    masked_identifier: str | None = Field(
        default=None,
        max_length=64,
        description="Masked identifier for display purposes only.",
    )
