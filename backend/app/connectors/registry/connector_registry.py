"""ConnectorRegistry — thread-safe, in-memory connector lifecycle registry.

Responsibilities:
  - Register connector instances by their stable connector_id
  - Prevent duplicate registration
  - Lookup connectors by id or type
  - List / deregister connectors

This is intentionally kept in-memory and lightweight.  A persistent
registry (backed by the DB) can be layered on top in a future phase.
"""

import logging
import threading
from typing import TYPE_CHECKING

from app.connectors.base.connector_exceptions import (
    ConnectorNotFoundError,
    DuplicateConnectorError,
)
from app.connectors.base.connector_types import ConnectorType

if TYPE_CHECKING:
    from app.connectors.base.base_connector import BaseConnector

logger = logging.getLogger("qorvexis.connectors.registry")


class ConnectorRegistry:
    """Central registry for all active connector instances."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connectors: dict[str, "BaseConnector"] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, connector: "BaseConnector") -> None:
        """Register a connector instance.

        Raises:
            DuplicateConnectorError if the connector_id is already registered.
        """
        with self._lock:
            if connector.connector_id in self._connectors:
                raise DuplicateConnectorError(
                    f"Connector '{connector.connector_id}' is already registered."
                )
            self._connectors[connector.connector_id] = connector
            logger.info(
                "registry.register id=%s type=%s",
                connector.connector_id,
                connector.connector_type.value,
            )

    def deregister(self, connector_id: str) -> None:
        """Remove a connector from the registry.

        Raises:
            ConnectorNotFoundError if the id is not registered.
        """
        with self._lock:
            if connector_id not in self._connectors:
                raise ConnectorNotFoundError(
                    f"Connector '{connector_id}' is not registered."
                )
            del self._connectors[connector_id]
            logger.info("registry.deregister id=%s", connector_id)

    # ── Lookup ────────────────────────────────────────────────────────────────

    def get(self, connector_id: str) -> "BaseConnector":
        """Retrieve a connector by id.

        Raises:
            ConnectorNotFoundError if not found.
        """
        with self._lock:
            connector = self._connectors.get(connector_id)
        if connector is None:
            raise ConnectorNotFoundError(
                f"Connector '{connector_id}' not found."
            )
        return connector

    def get_by_type(self, connector_type: ConnectorType) -> list["BaseConnector"]:
        """Return all registered connectors of a given type."""
        with self._lock:
            return [c for c in self._connectors.values() if c.connector_type == connector_type]

    def list_all(self) -> list["BaseConnector"]:
        """Return all registered connectors."""
        with self._lock:
            return list(self._connectors.values())

    def is_registered(self, connector_id: str) -> bool:
        with self._lock:
            return connector_id in self._connectors

    # ── Snapshot ──────────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "total": len(self._connectors),
                "connectors": [
                    {
                        "id":   c.connector_id,
                        "name": c.connector_name,
                        "type": c.connector_type.value,
                    }
                    for c in self._connectors.values()
                ],
            }


# ── Singleton ─────────────────────────────────────────────────────────────────
connector_registry = ConnectorRegistry()
