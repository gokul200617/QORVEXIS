"""OpenAI Connector Implementation."""

import logging
from typing import Optional

from app.connectors.base.base_connector import BaseConnector
from app.connectors.base.connector_status import ConnectorStatus
from app.connectors.base.connector_types import ConnectorType
from app.connectors.normalization.normalization_engine import normalization_engine
from app.connectors.openai.openai_client import OpenAIClient
from app.connectors.openai.openai_usage_service import openai_usage_service
# Import normalizer so it registers itself with the engine
import app.connectors.openai.openai_normalizer  # noqa: F401

logger = logging.getLogger("qorvexis.connectors.openai.connector")


class OpenAIConnector(BaseConnector):
    """Concrete implementation for OpenAI."""

    def __init__(self, connector_id: str, name: str, api_key: str):
        self._connector_id = connector_id
        self._name = name
        self._client = OpenAIClient(api_key=api_key)
        self._status = ConnectorStatus.DISCONNECTED

    @property
    def connector_id(self) -> str:
        return self._connector_id

    @property
    def connector_name(self) -> str:
        return self._name

    @property
    def connector_type(self) -> ConnectorType:
        return ConnectorType.AI_PROVIDER

    def authenticate(self) -> bool:
        """API keys are validated directly during validate()."""
        return True

    def validate(self) -> bool:
        """Validate the API key by attempting to fetch the models list."""
        success = self._client.validate_key()
        if success:
            self._status = ConnectorStatus.CONNECTED
        return success

    def collect_metrics(self) -> dict:
        """Fetch raw usage from the OpenAI API (or fallback simulation)."""
        return self._client.fetch_usage()

    def normalize(self, raw_data: dict) -> dict:
        """Map raw OpenAI telemetry to NormalizedTelemetry using the engine."""
        telemetry = normalization_engine.normalize(
            raw=raw_data,
            connector_id=self.connector_id,
            connector_name=self.connector_name,
            connector_type="openai"
        )
        
        # Tap into the usage service to aggregate token intelligence
        openai_usage_service.record_ingestion(telemetry)
        
        return telemetry.to_dict()

    def health_check(self) -> ConnectorStatus:
        """Check if the connection remains healthy."""
        try:
            if self._client.validate_key():
                self._status = ConnectorStatus.CONNECTED
        except Exception:
            self._status = ConnectorStatus.ERROR
        return self._status

    def disconnect(self) -> None:
        """Clear memory resident keys."""
        self._client = None
        self._status = ConnectorStatus.DISCONNECTED
        logger.info("openai.connector.disconnected id=%s", self.connector_id)
