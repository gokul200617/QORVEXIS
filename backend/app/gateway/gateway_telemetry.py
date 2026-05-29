"""Gateway Telemetry — fire-and-forget persistence layer.

Every proxied request calls gateway_telemetry.record() which persists to
GatewayRequestRecord asynchronously. Failures are silently absorbed to
preserve gateway throughput.
"""

from __future__ import annotations
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("qorvexis.gateway.telemetry")


@dataclass
class GatewayTelemetryEvent:
    provider:           str
    model:              str
    prompt_tokens:      int
    completion_tokens:  int
    total_tokens:       int
    estimated_cost:     float
    latency_ms:         float
    success:            bool = True
    cache_hit:          bool = False
    workload_id:        str | None = None
    workload_name:      str | None = None
    team_id:            str | None = None
    team_name:          str | None = None
    customer_id:        str | None = None
    customer_name:      str | None = None
    application_id:     str | None = None
    session_id:         str | None = None
    request_id:         str | None = None
    timestamp:          datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class GatewayTelemetryService:
    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gw_telemetry")
        self._failures = 0

    def record(self, event: GatewayTelemetryEvent) -> None:
        """Fire-and-forget telemetry persistence. Never raises."""
        if self._failures >= 50:
            # Silently drop after persistent DB failures
            return
        try:
            self._executor.submit(self._persist, event)
        except Exception:
            pass

    def _persist(self, event: GatewayTelemetryEvent) -> None:
        try:
            from app.database.session import SessionLocal
            from app.gateway.gateway_models import GatewayRequestRecord

            db = SessionLocal()
            try:
                record = GatewayRequestRecord(
                    workload_id=event.workload_id,
                    workload_name=event.workload_name,
                    team_id=event.team_id,
                    team_name=event.team_name,
                    customer_id=event.customer_id,
                    customer_name=event.customer_name,
                    application_id=event.application_id,
                    provider=event.provider,
                    model=event.model,
                    prompt_tokens=event.prompt_tokens,
                    completion_tokens=event.completion_tokens,
                    total_tokens=event.total_tokens,
                    estimated_cost=event.estimated_cost,
                    latency_ms=event.latency_ms,
                    session_id=event.session_id,
                    request_id=event.request_id,
                    success=event.success,
                    cache_hit=event.cache_hit,
                )
                db.add(record)
                db.commit()
                self._failures = 0
            except SQLAlchemyError:
                db.rollback()
                self._failures += 1
            finally:
                db.close()
        except Exception as exc:
            self._failures += 1
            logger.debug("gateway.telemetry.persist_failed error=%s", exc)


gateway_telemetry = GatewayTelemetryService()
