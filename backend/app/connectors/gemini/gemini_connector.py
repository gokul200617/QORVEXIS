"""Gemini Connector Implementation."""

import logging
from typing import Optional

from app.connectors.base.base_connector import BaseConnector
from app.connectors.base.connector_status import ConnectorStatus
from app.connectors.base.connector_types import ConnectorType
from app.connectors.gemini.gemini_client import GeminiClient
import app.connectors.gemini.gemini_normalizer  # noqa: F401

logger = logging.getLogger("qorvexis.connectors.gemini.connector")


class GeminiConnector(BaseConnector):
    """Concrete implementation for Google Gemini."""

    def __init__(self, connector_id: str, name: str, api_key: str, simulation_mode: bool = False):
        self._connector_id = connector_id
        self._name = name
        self._client = GeminiClient(api_key=api_key)
        self._status = ConnectorStatus.DISCONNECTED
        self._simulation_mode = simulation_mode

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
        return True

    def validate(self) -> bool:
        if self._simulation_mode:
            self._status = ConnectorStatus.CONNECTED
            return True
        success = self._client.validate_key()
        if success:
            self._status = ConnectorStatus.CONNECTED
        return success

    def collect_metrics(self) -> dict:
        """Fetch raw usage (fallback simulation for demo mode)."""
        if self._simulation_mode:
            return self._client.fetch_usage()
        return {}

    def normalize(self, raw_data: dict) -> dict:
        """Map raw Gemini telemetry. Real analytics bypass this layer."""
        return {}

    def health_check(self) -> ConnectorStatus:
        if self._simulation_mode:
            self._status = ConnectorStatus.CONNECTED
            return self._status
            
        try:
            if self._client.validate_key():
                self._status = ConnectorStatus.CONNECTED
        except Exception:
            self._status = ConnectorStatus.ERROR
        return self._status

    def disconnect(self) -> None:
        self._client = None
        self._status = ConnectorStatus.DISCONNECTED
        logger.info("gemini.connector.disconnected id=%s", self.connector_id)
