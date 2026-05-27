"""TelemetrySnapshot — normalized telemetry schema for Phase 7."""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TelemetrySnapshot:
    """Unified, normalized infrastructure telemetry snapshot.

    All fields are optional to allow graceful partial collection.
    No network IO fields — Phase 7 scope excludes them.
    """

    source: str = "local"
    provider: str = "local"
    host_identifier: str = field(default_factory=platform.node)
    timestamp: str = field(default_factory=_utc_now_iso)
    last_updated_at: str = field(default_factory=_utc_now_iso)

    # System metrics
    cpu_percent: float | None = None
    memory_percent: float | None = None
    memory_total_bytes: int | None = None
    memory_available_bytes: int | None = None
    disk_percent: float | None = None
    disk_total_bytes: int | None = None
    disk_free_bytes: int | None = None
    load_avg_1m: float | None = None
    load_avg_5m: float | None = None

    # GPU metrics
    gpu_available: bool = False
    gpu_percent: float | None = None
    gpu_memory_percent: float | None = None
    gpu_memory_used_bytes: int | None = None
    gpu_memory_total_bytes: int | None = None
    temperature_c: float | None = None
    power_watts: float | None = None
    gpu_device_name: str | None = None
    gpu_device_count: int = 0

    # Platform info
    platform: str | None = None
    python_version: str | None = None

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "provider": self.provider,
            "host_identifier": self.host_identifier,
            "timestamp": self.timestamp,
            "last_updated_at": self.last_updated_at,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "memory_total_bytes": self.memory_total_bytes,
            "memory_available_bytes": self.memory_available_bytes,
            "disk_percent": self.disk_percent,
            "disk_total_bytes": self.disk_total_bytes,
            "disk_free_bytes": self.disk_free_bytes,
            "load_avg_1m": self.load_avg_1m,
            "load_avg_5m": self.load_avg_5m,
            "gpu_available": self.gpu_available,
            "gpu_percent": self.gpu_percent,
            "gpu_memory_percent": self.gpu_memory_percent,
            "gpu_memory_used_bytes": self.gpu_memory_used_bytes,
            "gpu_memory_total_bytes": self.gpu_memory_total_bytes,
            "temperature_c": self.temperature_c,
            "power_watts": self.power_watts,
            "gpu_device_name": self.gpu_device_name,
            "gpu_device_count": self.gpu_device_count,
            "platform": self.platform,
            "python_version": self.python_version,
        }
