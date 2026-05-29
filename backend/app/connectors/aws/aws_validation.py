"""AWS credential and region validation — Phase 8D.

Wraps AWSClient.validate_credentials() in the Qorvexis validation
framework, ensuring health state is recorded correctly on both
success and failure.

RULE: This module NEVER activates simulation fallback.
      Validation must succeed with REAL credentials or fail explicitly.
"""

from __future__ import annotations

import logging

from app.connectors.aws.aws_client import AWSClient
from app.connectors.base.connector_exceptions import (
    ConnectorAuthError,
    ConnectorIngestionError,
)
from app.connectors.health.connector_health_service import connector_health_service

logger = logging.getLogger("qorvexis.connectors.aws.validation")


class AWSValidation:
    """Validates AWS credentials and region accessibility."""

    @staticmethod
    def validate(connector_id: str, client: AWSClient) -> tuple[bool, str]:
        """Run STS-based credential validation.

        Returns:
            (True, account_id)  on success
            (False, error_msg)  on failure

        Side effects:
            Records validation outcome with connector_health_service.
        """
        try:
            identity = client.validate_credentials()
            account_id = identity.get("account_id", "unknown")

            connector_health_service.record_validation(connector_id, True)
            logger.info(
                "aws.validation.success connector_id=%s account=%s",
                connector_id,
                account_id,
            )
            return True, account_id

        except ConnectorAuthError as exc:
            connector_health_service.record_validation(connector_id, False)
            logger.warning(
                "aws.validation.auth_failure connector_id=%s reason=%s",
                connector_id,
                exc,
            )
            return False, str(exc)

        except ConnectorIngestionError as exc:
            connector_health_service.record_validation(connector_id, False)
            logger.warning(
                "aws.validation.api_failure connector_id=%s reason=%s",
                connector_id,
                exc,
            )
            return False, str(exc)

        except Exception as exc:
            connector_health_service.record_validation(connector_id, False)
            logger.error(
                "aws.validation.unexpected_failure connector_id=%s detail=%s",
                connector_id,
                exc,
            )
            return False, f"Unexpected validation error: {exc}"


# ── Singleton ─────────────────────────────────────────────────────────────────
aws_validation = AWSValidation()
