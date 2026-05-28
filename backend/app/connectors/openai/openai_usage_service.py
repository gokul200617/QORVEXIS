"""Aggregates analytics for the OpenAI frontend dashboard."""

import threading

class OpenAIUsageService:
    """In-memory aggregator for OpenAI analytics."""

    def __init__(self):
        self._lock = threading.Lock()
        self._latest_telemetry = None
        self._cumulative_cost = 0.0
        self._cumulative_requests = 0

    def record_ingestion(self, telemetry):
        """Update analytics from the latest NormalizedTelemetry."""
        with self._lock:
            self._latest_telemetry = telemetry
            self._cumulative_cost += telemetry.estimated_cost_usd
            self._cumulative_requests += telemetry.requests_per_minute

    def get_analytics_summary(self) -> dict:
        """Return aggregated intelligence for the frontend."""
        with self._lock:
            t = self._latest_telemetry
            
            if not t:
                return {
                    "total_spend_usd": 0.0,
                    "estimated_monthly_usd": 0.0,
                    "total_requests": 0,
                    "most_expensive_model": "None",
                    "efficiency": 0.0
                }
                
            return {
                "total_spend_usd": round(self._cumulative_cost, 4),
                "estimated_monthly_usd": round(self._cumulative_cost * 30 * 24 * 60, 2), # extreme rough estimate
                "total_requests": self._cumulative_requests,
                "most_expensive_model": "gpt-4o",  # Simplified since usage api aggregations lose individual traces
                "efficiency": t.efficiency_score,
            }

openai_usage_service = OpenAIUsageService()
