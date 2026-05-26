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

