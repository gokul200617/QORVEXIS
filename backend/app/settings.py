from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Qorvexis API"
    supabase_url: str | None = None
    database_url: str
    gemini_api_key: str | None = None
    groq_api_key: str | None = None
    provider_timeout_seconds: int = 30
    max_concurrent_requests: int = 2
    gemini_max_concurrency: int = 1
    groq_max_concurrency: int = 1
    cors_origins_raw: str = "http://127.0.0.1:5500,http://localhost:5500"

    # Phase 5 — Operational Intelligence
    cache_ttl_seconds: int = 300
    cache_max_entries: int = 256
    dedup_window_seconds: int = 30
    provider_cooldown_seconds: int = 60

    # Phase 6 - Reliability & Persistence Hardening
    session_ttl_seconds: int = 86400
    session_max_requests: int = 80
    session_cleanup_batch_size: int = 40
    historical_metrics_window: int = 240
    historical_metrics_file: str = "operational_history.jsonl"
    stale_execution_seconds: int = 300
    request_timeout_seconds: int = 120
    queue_max_depth: int = 2500
    queue_enqueue_timeout_seconds: int = 2
    queue_drain_timeout_seconds: int = 300

    # Phase 7 — Infrastructure Telemetry
    telemetry_enabled: bool = True
    telemetry_persist_snapshots: bool = True
    telemetry_persist_interval_seconds: int = 300
    telemetry_gpu_idle_threshold: float = 10.0
    telemetry_cpu_high_threshold: float = 85.0
    telemetry_ram_high_threshold: float = 90.0
    telemetry_cache_low_threshold: float = 30.0
    telemetry_queue_pressure_threshold: float = 0.80

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins_raw.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
