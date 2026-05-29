"""Lightweight HTTP client for Groq telemetry validation."""

import logging
import httpx
from datetime import datetime, timezone

from app.connectors.base.connector_exceptions import (
    ConnectorAuthError,
    ConnectorTimeoutError,
    ConnectorIngestionError,
)

logger = logging.getLogger("qorvexis.connectors.groq.client")

class GroqClient:
    """Wrapper for Groq API calls for connector validation."""

    BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(self, api_key: str, timeout_sec: int = 10):
        self.api_key = api_key
        self.timeout = timeout_sec
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def validate_key(self) -> bool:
        """Hits the /v1/models endpoint to verify the API key is active."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(f"{self.BASE_URL}/models", headers=self.headers)
            
            if res.status_code == 401:
                raise ConnectorAuthError("Invalid Groq API Key provided.")
            
            res.raise_for_status()
            return True
            
        except httpx.TimeoutException as exc:
            raise ConnectorTimeoutError("Timeout reaching Groq API.") from exc
        except httpx.HTTPError as exc:
            raise ConnectorIngestionError(f"HTTP error during validation: {exc}") from exc

    def fetch_usage(self) -> dict:
        """Fetch token usage telemetry.
        
        Since real analytics will come from Qorvexis' internal TokenTelemetryRecord DB,
        this method provides simulated fallback data just for demonstration mode.
        """
        import random
        
        data = []
        now = int(datetime.now(timezone.utc).timestamp())
        
        for _ in range(5):
            data.append({
                "timestamp": now - random.randint(0, 3600),
                "n_requests": random.randint(10, 100),
                "operation": "chat.completions",
                "snapshot_id": "llama3-70b-8192" if random.random() > 0.5 else "mixtral-8x7b-32768",
                "n_context_tokens_total": random.randint(10000, 50000),
                "n_generated_tokens_total": random.randint(2000, 10000),
                "estimated_latency_ms": random.randint(150, 400),
            })
            
        return {
            "data": data,
            "has_more": False
        }
