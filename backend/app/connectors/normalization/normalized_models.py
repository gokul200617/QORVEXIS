"""NormalizedTelemetry — Qorvexis universal telemetry schema.

All connectors map their provider-specific payloads into this shared model.
This decouples the dashboard, analytics, and storage layers from any
specific provider format.

Fields deliberately kept at a shared conceptual level — not provider-specific.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class NormalizedTelemetry:
    """Canonical telemetry representation shared across all connectors.

    All float fields are 0.0 when not applicable for a given connector type.
    All optional fields are None when the source system does not provide them.
    """

    # ── Source metadata ───────────────────────────────────────────────────────
    connector_id:   str = ""
    connector_name: str = ""
    connector_type: str = ""
    collected_at:   datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ── Utilization (0–100 %) ─────────────────────────────────────────────────
    cpu_utilization_pct:    float = 0.0
    memory_utilization_pct: float = 0.0
    gpu_utilization_pct:    float = 0.0
    disk_utilization_pct:   float = 0.0

    # ── Throughput ────────────────────────────────────────────────────────────
    requests_per_minute: float = 0.0
    tokens_per_minute:   float = 0.0
    bytes_transferred:   int   = 0

    # ── Latency (ms) ─────────────────────────────────────────────────────────
    average_latency_ms: float = 0.0
    p95_latency_ms:     float | None = None
    p99_latency_ms:     float | None = None

    # ── Token usage ───────────────────────────────────────────────────────────
    total_prompt_tokens:    int = 0
    total_response_tokens:  int = 0
    total_tokens:           int = 0

    # ── Cost ─────────────────────────────────────────────────────────────────
    estimated_cost_usd:       float = 0.0
    estimated_monthly_usd:    float | None = None

    # ── Derived scores (0–100) ────────────────────────────────────────────────
    efficiency_score:   float = 0.0   # higher = better utilization
    waste_score:        float = 0.0   # higher = more idle waste
    health_score:       float = 100.0 # overall health (100 = perfect)
    reliability_score:  float = 100.0 # success rate (100 = perfect)

    # ── Provider-specific extras (pass-through) ───────────────────────────────
    raw_extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "connector_id":             self.connector_id,
            "connector_name":           self.connector_name,
            "connector_type":           self.connector_type,
            "collected_at":             self.collected_at.isoformat(),
            "cpu_utilization_pct":      self.cpu_utilization_pct,
            "memory_utilization_pct":   self.memory_utilization_pct,
            "gpu_utilization_pct":      self.gpu_utilization_pct,
            "disk_utilization_pct":     self.disk_utilization_pct,
            "requests_per_minute":      self.requests_per_minute,
            "tokens_per_minute":        self.tokens_per_minute,
            "bytes_transferred":        self.bytes_transferred,
            "average_latency_ms":       self.average_latency_ms,
            "p95_latency_ms":           self.p95_latency_ms,
            "p99_latency_ms":           self.p99_latency_ms,
            "total_prompt_tokens":      self.total_prompt_tokens,
            "total_response_tokens":    self.total_response_tokens,
            "total_tokens":             self.total_tokens,
            "estimated_cost_usd":       self.estimated_cost_usd,
            "estimated_monthly_usd":    self.estimated_monthly_usd,
            "efficiency_score":         self.efficiency_score,
            "waste_score":              self.waste_score,
            "health_score":             self.health_score,
            "reliability_score":        self.reliability_score,
        }
