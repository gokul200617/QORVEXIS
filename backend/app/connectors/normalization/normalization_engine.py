"""NormalizationEngine — coerces connector raw output → NormalizedTelemetry.

Phase 8A: provides a generic best-effort normalization pass using
field-name conventions shared across provider schemas.

Future phases will register provider-specific transform functions into
the engine for precise, tested field mappings.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.connectors.normalization.mapping_helpers import (
    clamp,
    safe_float,
    safe_int,
)
from app.connectors.normalization.normalized_models import NormalizedTelemetry

logger = logging.getLogger("qorvexis.connectors.normalization")

# Field aliases: common provider field names → NormalizedTelemetry field names.
# The engine tries each alias in order until it finds a non-None value.
_FIELD_ALIASES: dict[str, list[str]] = {
    "cpu_utilization_pct":    ["cpu_percent", "cpu_utilization", "cpu_usage_percent"],
    "memory_utilization_pct": ["memory_percent", "memory_utilization", "ram_percent"],
    "gpu_utilization_pct":    ["gpu_percent", "gpu_utilization", "gpu_usage_percent"],
    "disk_utilization_pct":   ["disk_percent", "disk_utilization"],
    "requests_per_minute":    ["requests_per_minute", "rpm", "request_rate"],
    "average_latency_ms":     ["average_latency_ms", "avg_latency_ms", "mean_latency"],
    "total_prompt_tokens":    ["total_prompt_tokens", "prompt_tokens", "input_tokens"],
    "total_response_tokens":  ["total_response_tokens", "response_tokens", "output_tokens", "completion_tokens"],
    "estimated_cost_usd":     ["estimated_cost_usd", "total_cost", "cost_usd", "total_estimated_cost"],
    "efficiency_score":       ["efficiency_score", "efficiency"],
    "waste_score":            ["waste_score", "idle_score"],
    "health_score":           ["health_score", "orchestration_health_score"],
    "reliability_score":      ["reliability_score", "success_rate"],
}


def _extract(raw: dict, aliases: list[str], default: float = 0.0) -> float:
    for alias in aliases:
        value = raw.get(alias)
        if value is not None:
            return safe_float(value, default)
    return default


class NormalizationEngine:
    """Normalizes raw connector output into a NormalizedTelemetry instance."""

    # ── Provider-specific transforms registry ─────────────────────────────────
    # Maps connector_type string → callable(raw: dict) -> dict
    # Phase 8A: empty — Phase 8B adds OpenAI/AWS-specific transforms.
    _transforms: dict[str, any] = {}

    @classmethod
    def register_transform(cls, connector_type: str, fn: callable) -> None:
        """Register a provider-specific pre-processing transform."""
        cls._transforms[connector_type] = fn
        logger.info("normalization.transform_registered type=%s", connector_type)

    def normalize(
        self,
        raw: dict,
        connector_id: str = "",
        connector_name: str = "",
        connector_type: str = "",
    ) -> NormalizedTelemetry:
        """Normalize raw connector data into NormalizedTelemetry.

        1. Optionally applies a registered provider-specific transform.
        2. Uses alias-based field extraction as the fallback.
        """
        # Step 1: apply provider-specific transform if registered
        if connector_type in self._transforms:
            try:
                raw = self._transforms[connector_type](raw)
            except Exception as exc:
                logger.warning(
                    "normalization.transform_failed type=%s error=%s",
                    connector_type,
                    exc,
                )

        # Step 2: generic alias-based extraction
        prompt_tokens   = safe_int(_extract(raw, _FIELD_ALIASES["total_prompt_tokens"]))
        response_tokens = safe_int(_extract(raw, _FIELD_ALIASES["total_response_tokens"]))

        telemetry = NormalizedTelemetry(
            connector_id=connector_id,
            connector_name=connector_name,
            connector_type=connector_type,
            collected_at=datetime.now(timezone.utc),

            cpu_utilization_pct=    clamp(_extract(raw, _FIELD_ALIASES["cpu_utilization_pct"])),
            memory_utilization_pct= clamp(_extract(raw, _FIELD_ALIASES["memory_utilization_pct"])),
            gpu_utilization_pct=    clamp(_extract(raw, _FIELD_ALIASES["gpu_utilization_pct"])),
            disk_utilization_pct=   clamp(_extract(raw, _FIELD_ALIASES["disk_utilization_pct"])),

            requests_per_minute=    _extract(raw, _FIELD_ALIASES["requests_per_minute"]),
            average_latency_ms=     _extract(raw, _FIELD_ALIASES["average_latency_ms"]),

            total_prompt_tokens=    prompt_tokens,
            total_response_tokens=  response_tokens,
            total_tokens=           prompt_tokens + response_tokens,

            estimated_cost_usd=     _extract(raw, _FIELD_ALIASES["estimated_cost_usd"]),

            efficiency_score=       clamp(_extract(raw, _FIELD_ALIASES["efficiency_score"])),
            waste_score=            clamp(_extract(raw, _FIELD_ALIASES["waste_score"])),
            health_score=           clamp(_extract(raw, _FIELD_ALIASES["health_score"]), 0.0, 100.0),
            reliability_score=      clamp(_extract(raw, _FIELD_ALIASES["reliability_score"]), 0.0, 100.0),

            raw_extras={},
        )

        logger.debug(
            "normalization.complete id=%s health=%.1f efficiency=%.1f",
            connector_id,
            telemetry.health_score,
            telemetry.efficiency_score,
        )

        return telemetry


# ── Singleton ─────────────────────────────────────────────────────────────────
normalization_engine = NormalizationEngine()
