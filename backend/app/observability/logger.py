import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.observability.tracing import get_trace_context


def _json_default(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def log_event(logger: logging.Logger, level: str, event: str, **fields: Any) -> None:
    payload = {
        "event": event,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        **{key: value for key, value in get_trace_context().items() if value is not None},
        **fields,
    }
    message = json.dumps(payload, default=_json_default, sort_keys=True)
    getattr(logger, level)(message)


def orchestration_payload(
    *,
    request_id: int | str | None,
    session_id: str | None = None,
    provider: str | None = None,
    lifecycle_state: str | None = None,
    queue_wait_ms: int | None = None,
    execution_duration_ms: int | None = None,
    fallback_used: bool | None = None,
    cache_hit: bool | None = None,
    reconciliation_state: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "session_id": session_id,
        "provider": provider,
        "lifecycle_state": lifecycle_state,
        "queue_wait_ms": queue_wait_ms,
        "execution_duration_ms": execution_duration_ms,
        "fallback_used": fallback_used,
        "cache_hit": cache_hit,
        "reconciliation_state": reconciliation_state,
        **fields,
    }
