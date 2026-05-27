"""Telemetry normalizer — merges system and GPU collectors into TelemetrySnapshot."""

import logging

from app.telemetry.collectors.gpu_collector import collect_gpu_metrics
from app.telemetry.collectors.system_collector import collect_system_metrics
from app.telemetry.normalizers.schema import TelemetrySnapshot

logger = logging.getLogger("qorvexis.telemetry.normalizer")


class TelemetryNormalizer:
    """Collects from all local sources and normalizes into TelemetrySnapshot.

    Each collector is called in an isolated try/except.
    A valid TelemetrySnapshot is always returned — fields may be None
    if the underlying collector failed.
    """

    def collect_and_normalize(self) -> TelemetrySnapshot:
        snapshot = TelemetrySnapshot()

        # System metrics
        try:
            sys_data = collect_system_metrics()
            snapshot.cpu_percent = sys_data.get("cpu_percent")
            snapshot.memory_percent = sys_data.get("memory_percent")
            snapshot.memory_total_bytes = sys_data.get("memory_total_bytes")
            snapshot.memory_available_bytes = sys_data.get("memory_available_bytes")
            snapshot.disk_percent = sys_data.get("disk_percent")
            snapshot.disk_total_bytes = sys_data.get("disk_total_bytes")
            snapshot.disk_free_bytes = sys_data.get("disk_free_bytes")
            snapshot.load_avg_1m = sys_data.get("load_avg_1m")
            snapshot.load_avg_5m = sys_data.get("load_avg_5m")
            snapshot.platform = sys_data.get("platform")
            snapshot.python_version = sys_data.get("python_version")
        except Exception as exc:
            logger.warning("normalizer.system_collection_failed error=%s", exc)

        # GPU metrics
        try:
            gpu_data = collect_gpu_metrics()
            snapshot.gpu_available = gpu_data.get("available", False)
            if snapshot.gpu_available:
                snapshot.gpu_percent = gpu_data.get("gpu_percent")
                snapshot.gpu_memory_percent = gpu_data.get("gpu_memory_percent")
                snapshot.gpu_memory_used_bytes = gpu_data.get("gpu_memory_used_bytes")
                snapshot.gpu_memory_total_bytes = gpu_data.get("gpu_memory_total_bytes")
                snapshot.temperature_c = gpu_data.get("temperature_c")
                snapshot.power_watts = gpu_data.get("power_watts")
                snapshot.gpu_device_name = gpu_data.get("device_name")
                snapshot.gpu_device_count = gpu_data.get("device_count", 0)
        except Exception as exc:
            logger.warning("normalizer.gpu_collection_failed error=%s", exc)

        logger.debug(
            "telemetry.collected cpu=%.1f mem=%.1f disk=%.1f gpu_available=%s",
            snapshot.cpu_percent or 0,
            snapshot.memory_percent or 0,
            snapshot.disk_percent or 0,
            snapshot.gpu_available,
        )

        return snapshot


# Module-level singleton
telemetry_normalizer = TelemetryNormalizer()
