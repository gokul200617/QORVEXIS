"""Token Tracking Service.

Ingests request-level token telemetry asynchronously and failure-safely.
Uses background tasks/threads to avoid blocking orchestration.
"""

import logging
import time
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func
from app.database.session import SessionLocal

from app.token_intelligence.schemas.token_schema import TokenTelemetryCreate
from app.token_intelligence.models.token_tracking import TokenTelemetryRecord
from app.token_intelligence.models.workload_signature import WorkloadSignatureRecord
from app.token_intelligence.utils.hashing import generate_signature
from app.token_intelligence.analytics.request_classifier import classify_request
from app.token_intelligence.pricing.pricing_engine import estimate_cost
from app.token_intelligence.analytics.anomaly_engine import detect_anomalies

logger = logging.getLogger("qorvexis.token_intelligence.tracker")


class TelemetryCircuitBreaker:
    """Lightweight in-memory circuit breaker to prevent DB pressure during outages."""
    def __init__(self, failure_threshold: int = 10, cooldown_seconds: int = 30):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.failures = 0
        self.last_failure_time = 0.0
        self.suppressed_warnings = 0

    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()

    def record_success(self):
        if self.failures > 0:
            if self.suppressed_warnings > 0:
                logger.info(f"Telemetry ingestion recovered. (Suppressed {self.suppressed_warnings} warnings)")
        self.failures = 0
        self.suppressed_warnings = 0

    def is_open(self) -> bool:
        if self.failures >= self.failure_threshold:
            if time.time() - self.last_failure_time < self.cooldown_seconds:
                self.suppressed_warnings += 1
                if self.suppressed_warnings % 50 == 0:
                    logger.warning(f"Telemetry ingestion paused: {self.failures} consecutive failures. (Suppressed {self.suppressed_warnings} warnings)")
                return True
            else:
                # Half-open state
                return False
        return False


class TokenTrackingService:
    """Best-effort telemetry ingestion service."""
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="token_ingest")
        self.circuit_breaker = TelemetryCircuitBreaker()

    def record_telemetry(self, telemetry: TokenTelemetryCreate) -> None:
        """Fire-and-forget method to persist token telemetry."""
        if self.circuit_breaker.is_open():
            return
            
        try:
            self.executor.submit(self._ingest_with_retry, telemetry)
        except Exception as exc:
            logger.warning(
                "token_intelligence.submit_failed service=token_tracking "
                "event=executor_queue_full exception_type=%s message=%s",
                type(exc).__name__, exc,
            )

    def _ingest_with_retry(self, data: TokenTelemetryCreate) -> None:
        retries = 1
        for attempt in range(retries + 1):
            try:
                self._ingest_safely(data)
                self.circuit_breaker.record_success()
                return
            except Exception as exc:
                if attempt == retries:
                    self.circuit_breaker.record_failure()
                    if self.circuit_breaker.suppressed_warnings == 0:
                        logger.warning(f"token_intelligence.ingest_failed final_error={exc}")
                else:
                    time.sleep(0.5)

    def _ingest_safely(self, data: TokenTelemetryCreate) -> None:
        """Isolated safe ingestion routine."""
        db = SessionLocal()
        
        try:
            # Optional Enforce bounded timeout on this session transaction if adapter supports it
            db.connection(execution_options={"timeout": 2})
            
            # 1. Compute deterministic signature safely
            signature = None
            category = data.request_category
            
            try:
                if data.prompt_text:
                    signature = generate_signature(data.prompt_text)
                    if not category:
                        category = classify_request(
                            data.prompt_text, 
                            data.prompt_tokens, 
                            data.completion_tokens, 
                            data.model
                        )
            except Exception as exc:
                logger.debug(
                    "token_intelligence.signature_failed service=token_tracking "
                    "event=signature_generation_skipped exception_type=%s message=%s",
                    type(exc).__name__, exc,
                )

            # 2. Compute true pricing
            cost = data.estimated_cost
            try:
                if cost == 0.0 and (data.prompt_tokens > 0 or data.completion_tokens > 0):
                    cost = estimate_cost(data.provider, data.model, data.prompt_tokens, data.completion_tokens)
            except Exception as exc:
                logger.debug(
                    "token_intelligence.cost_estimation_failed service=token_tracking "
                    "event=cost_skipped exception_type=%s message=%s",
                    type(exc).__name__, exc,
                )

            # 3. Compute inflation ratio
            inflation_ratio = None
            if data.prompt_tokens > 0:
                inflation_ratio = data.completion_tokens / data.prompt_tokens

            # 4. Anomaly Check Safely
            try:
                anomalies = detect_anomalies(data.prompt_tokens, data.completion_tokens, cost, data.model, data.provider)
                for anomaly in anomalies:
                    level = logging.WARNING if anomaly["severity"] == "warning" else logging.ERROR
                    logger.log(level, f"token_anomaly type={anomaly['type']} detail='{anomaly['detail']}'")
            except Exception as exc:
                logger.debug(
                    "token_intelligence.anomaly_check_failed service=token_tracking "
                    "event=anomaly_detection_skipped exception_type=%s message=%s",
                    type(exc).__name__, exc,
                )

            # 5. Persist Workload Signature stats
            if signature:
                sig_record = db.query(WorkloadSignatureRecord).filter(WorkloadSignatureRecord.signature == signature).first()
                if sig_record:
                    sig_record.occurrence_count += 1
                    sig_record.last_seen = func.now()
                else:
                    sig_record = WorkloadSignatureRecord(
                        signature=signature,
                        occurrence_count=1,
                        example_category=category
                    )
                    db.add(sig_record)

            # 6. Persist Request Telemetry
            record = TokenTelemetryRecord(
                provider=data.provider or "unknown",
                model=data.model or "unknown",
                prompt_tokens=data.prompt_tokens,
                completion_tokens=data.completion_tokens,
                total_tokens=data.total_tokens,
                estimated_cost=cost,
                latency_ms=data.latency_ms,
                execution_duration_ms=data.execution_duration_ms,
                request_category=category,
                cache_hit=data.cache_hit,
                fallback_used=data.fallback_used,
                deduplicated=data.deduplicated,
                workload_signature=signature,
                session_id=str(data.session_id) if data.session_id else None,
                request_id=str(data.request_id) if data.request_id else None,
                completion_inflation_ratio=inflation_ratio
            )
            db.add(record)
            
            db.commit()
            
        except SQLAlchemyError as exc:
            db.rollback()
            raise exc
        except Exception as exc:
            db.rollback()
            raise exc
        finally:
            db.close()

token_tracking_service = TokenTrackingService()
