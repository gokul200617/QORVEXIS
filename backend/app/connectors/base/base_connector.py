"""Abstract base connector contract.

All future connectors (OpenAIConnector, AWSConnector, etc.) MUST subclass
BaseConnector and implement each abstract method.  The framework calls
these methods in a defined lifecycle order:

  authenticate() → validate() → collect_metrics() → normalize() → sync()

and separately:

  health_check() / disconnect()
"""

import logging
from abc import ABC, abstractmethod

from app.connectors.base.connector_status import ConnectorStatus
from app.connectors.base.connector_types import ConnectorType
from app.connectors.base.ingestion_result import IngestionResult

logger = logging.getLogger("qorvexis.connectors.base")


class BaseConnector(ABC):
    """Abstract contract that every Qorvexis connector must satisfy.

    Subclasses should be lightweight data objects — they hold only
    configuration/credential references, never raw secrets in plaintext.
    """

    # ── Identity ─────────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def connector_id(self) -> str:
        """Stable unique identifier (e.g. 'openai-prod', 'aws-us-east-1')."""

    @property
    @abstractmethod
    def connector_name(self) -> str:
        """Human-readable display name."""

    @property
    @abstractmethod
    def connector_type(self) -> ConnectorType:
        """Category this connector belongs to."""

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    @abstractmethod
    def authenticate(self) -> bool:
        """Establish authentication with the external system.

        Returns:
            True if authentication succeeded.
        Raises:
            ConnectorAuthError on failure.
        """

    @abstractmethod
    def validate(self) -> bool:
        """Validate that credentials/config are correct and the endpoint
        is reachable before the first sync.

        Returns:
            True if validation passed.
        Raises:
            ConnectorValidationError on failure.
        """

    @abstractmethod
    def collect_metrics(self) -> dict:
        """Fetch raw telemetry from the external system.

        Returns:
            Raw dictionary of provider-specific metrics.
        Raises:
            ConnectorIngestionError on failure.
        """

    @abstractmethod
    def normalize(self, raw_data: dict) -> dict:
        """Map provider-specific raw data to Qorvexis normalized schema.

        Args:
            raw_data: Output from collect_metrics().
        Returns:
            Dictionary conforming to NormalizedTelemetry fields.
        """

    @abstractmethod
    def health_check(self) -> ConnectorStatus:
        """Perform a lightweight liveness check against the external system.

        Returns:
            Current ConnectorStatus.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Gracefully close any open connections/sessions."""

    # ── Composite sync ────────────────────────────────────────────────────────

    def sync(self) -> IngestionResult:
        """Run the full ingestion cycle: collect → normalize → return result.

        This default implementation is intentionally simple and synchronous.
        Subclasses may override for provider-specific retry/pagination logic.
        """
        import time
        t0 = time.monotonic()

        try:
            raw       = self.collect_metrics()
            normalized = self.normalize(raw)
            duration_ms = int((time.monotonic() - t0) * 1000)

            logger.info(
                "connector.sync.success id=%s type=%s duration_ms=%s",
                self.connector_id,
                self.connector_type.value,
                duration_ms,
            )

            return IngestionResult(
                connector_id=self.connector_id,
                connector_name=self.connector_name,
                success=True,
                records_ingested=1,
                duration_ms=duration_ms,
                normalized_data=normalized,
            )

        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.warning(
                "connector.sync.failed id=%s error=%s",
                self.connector_id,
                exc,
            )
            return IngestionResult(
                connector_id=self.connector_id,
                connector_name=self.connector_name,
                success=False,
                duration_ms=duration_ms,
                error_message=str(exc),
            )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.connector_id!r} type={self.connector_type.value!r}>"
