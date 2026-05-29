"""Lightweight HTTP client for Gemini telemetry validation."""

import logging
import httpx
from datetime import datetime, timezone

from app.connectors.base.connector_exceptions import (
    ConnectorAuthError,
    ConnectorTimeoutError,
    ConnectorIngestionError,
)

logger = logging.getLogger("qorvexis.connectors.gemini.client")

class GeminiClient:
    """Wrapper for Gemini API calls for connector validation."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str, timeout_sec: int = 10):
        self.api_key = api_key
        self.timeout = timeout_sec

    def validate_key(self) -> bool:
        """Hits the /models endpoint to verify the API key is active."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(f"{self.BASE_URL}/models?key={self.api_key}")
            
            if res.status_code in (400, 403):
                raise ConnectorAuthError("Invalid Gemini API Key provided.")
            
            res.raise_for_status()
            return True
            
        except httpx.TimeoutException as exc:
            raise ConnectorTimeoutError("Timeout reaching Gemini API.") from exc
        except httpx.HTTPError as exc:
            raise ConnectorIngestionError(f"HTTP error during validation: {exc}") from exc

    def fetch_usage(self) -> dict:
        """Fetch token usage telemetry for demo simulation.
        Real analytics run off TokenTelemetryRecord.
        """
        import random
        
        data = []
        now = int(datetime.now(timezone.utc).timestamp())
        
        for _ in range(5):
            data.append({
                "timestamp": now - random.randint(0, 3600),
                "n_requests": random.randint(10, 80),
                "operation": "generateContent",
                "snapshot_id": "gemini-1.5-pro" if random.random() > 0.5 else "gemini-1.5-flash",
                "n_context_tokens_total": random.randint(20000, 100000),
                "n_generated_tokens_total": random.randint(1000, 8000),
                "estimated_latency_ms": random.randint(400, 1500),
            })
            
        return {
            "data": data,
            "has_more": False
        }
