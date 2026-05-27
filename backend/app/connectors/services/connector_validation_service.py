"""ValidationService — safe execution of connector validation checks."""

import logging

from app.connectors.base.base_connector import BaseConnector
from app.connectors.base.connector_exceptions import ConnectorValidationError
from app.connectors.health.connector_health_service import connector_health_service

logger = logging.getLogger("qorvexis.connectors.validation")


class ConnectorValidationService:
    """Orchestrates configuration and credential validation for connectors."""

    @staticmethod
    def validate(connector: BaseConnector) -> bool:
        """Run the connector's validate() method safely and record the outcome."""
        try:
            logger.info("validation.start id=%s", connector.connector_id)
            
            # Step 1: Ensure authentication context can be established
            connector.authenticate()
            
            # Step 2: Perform endpoint / credential validation
            passed = connector.validate()
            
            connector_health_service.record_validation(connector.connector_id, passed)
            
            logger.info(
                "validation.complete id=%s passed=%s", 
                connector.connector_id, 
                passed,
            )
            return passed
            
        except ConnectorValidationError as exc:
            logger.warning(
                "validation.failed id=%s reason='validation error' detail=%s", 
                connector.connector_id, 
                exc,
            )
            connector_health_service.record_validation(connector.connector_id, False)
            return False
            
        except Exception as exc:
            logger.error(
                "validation.failed id=%s reason='unexpected error' detail=%s", 
                connector.connector_id, 
                exc,
            )
            connector_health_service.record_validation(connector.connector_id, False)
            return False


# ── Singleton ─────────────────────────────────────────────────────────────────
connector_validation_service = ConnectorValidationService()
