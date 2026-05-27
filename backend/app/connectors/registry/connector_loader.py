"""ConnectorLoader — future plugin-style connector class resolution.

Phase 8A: resolves connector classes from a static built-in map.
Future phases can replace this with importlib-based dynamic discovery.
"""

import logging
from typing import TYPE_CHECKING

from app.connectors.base.connector_exceptions import ConnectorNotFoundError

if TYPE_CHECKING:
    from app.connectors.base.base_connector import BaseConnector

logger = logging.getLogger("qorvexis.connectors.loader")

# ── Built-in connector class registry ─────────────────────────────────────────
# Phase 8A: empty — concrete connectors will be added in Phase 8B+.
# Key: string slug, Value: class reference
_CONNECTOR_CLASS_MAP: dict[str, type] = {}


class ConnectorLoader:
    """Resolves connector classes by type slug."""

    @staticmethod
    def load(connector_type: str) -> type:
        """Return the connector class for the given type slug.

        Args:
            connector_type: e.g. 'openai', 'aws', 'prometheus'

        Raises:
            ConnectorNotFoundError if the type is not registered.
        """
        cls = _CONNECTOR_CLASS_MAP.get(connector_type)
        if cls is None:
            available = list(_CONNECTOR_CLASS_MAP.keys()) or ["none yet"]
            raise ConnectorNotFoundError(
                f"No connector implementation for type '{connector_type}'. "
                f"Available: {available}"
            )
        logger.debug("loader.resolved type=%s class=%s", connector_type, cls.__name__)
        return cls

    @staticmethod
    def register_class(type_slug: str, cls: type) -> None:
        """Register a connector class under a type slug (used in future phases)."""
        _CONNECTOR_CLASS_MAP[type_slug] = cls
        logger.info("loader.class_registered type=%s class=%s", type_slug, cls.__name__)

    @staticmethod
    def available_types() -> list[str]:
        return list(_CONNECTOR_CLASS_MAP.keys())
