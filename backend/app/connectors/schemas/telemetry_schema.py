"""API schemas mapping NormalizedTelemetry for HTTP responses."""

from datetime import datetime
from pydantic import BaseModel


class NormalizedTelemetrySchema(BaseModel):
    """Pydantic representation of NormalizedTelemetry."""
    connector_id:   str
    connector_name: str
    connector_type: str
    collected_at:   datetime

    cpu_utilization_pct:    float
    memory_utilization_pct: float
    gpu_utilization_pct:    float
    disk_utilization_pct:   float

    requests_per_minute: float
    tokens_per_minute:   float
    bytes_transferred:   int

    average_latency_ms: float
    p95_latency_ms:     float | None
    p99_latency_ms:     float | None

    total_prompt_tokens:    int
    total_response_tokens:  int
    total_tokens:           int

    estimated_cost_usd:       float
    estimated_monthly_usd:    float | None

    efficiency_score:   float
    waste_score:        float
    health_score:       float
    reliability_score:  float


class ConnectorTelemetryResponse(BaseModel):
    """API response wrapper for normalized connector telemetry."""
    connector_id: str
    telemetry: NormalizedTelemetrySchema
    is_stale: bool
