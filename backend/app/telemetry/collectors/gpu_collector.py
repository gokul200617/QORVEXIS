"""GPU metrics collector — optional pynvml, always degrades gracefully.

pynvml is imported INSIDE the function body only.
It is never imported at module level.
Startup is never affected by GPU library availability.
"""

import logging

logger = logging.getLogger("qorvexis.telemetry.gpu")

_UNAVAILABLE: dict = {"available": False}


def collect_gpu_metrics() -> dict:
    """Collect GPU metrics if pynvml is available.

    Returns {"available": False} on any failure — never raises.
    """
    try:
        import pynvml  # noqa: PLC0415 — lazy load, never at module level

        pynvml.nvmlInit()
        device_count = pynvml.nvmlDeviceGetCount()

        if device_count == 0:
            return {**_UNAVAILABLE, "reason": "no_gpu_devices"}

        # Collect metrics for first GPU (primary device)
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)

        utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
        memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)

        gpu_percent = float(utilization.gpu)
        gpu_memory_percent = round(
            (memory_info.used / memory_info.total) * 100, 2
        ) if memory_info.total > 0 else 0.0

        temperature_c: float | None = None
        try:
            temperature_c = float(
                pynvml.nvmlDeviceGetTemperature(
                    handle, pynvml.NVML_TEMPERATURE_GPU
                )
            )
        except Exception:
            pass

        power_watts: float | None = None
        try:
            power_mw = pynvml.nvmlDeviceGetPowerUsage(handle)
            power_watts = round(power_mw / 1000.0, 2)
        except Exception:
            pass

        device_name: str | None = None
        try:
            device_name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(device_name, bytes):
                device_name = device_name.decode("utf-8")
        except Exception:
            pass

        pynvml.nvmlShutdown()

        return {
            "available": True,
            "device_count": device_count,
            "device_name": device_name,
            "gpu_percent": gpu_percent,
            "gpu_memory_percent": gpu_memory_percent,
            "gpu_memory_used_bytes": memory_info.used,
            "gpu_memory_total_bytes": memory_info.total,
            "temperature_c": temperature_c,
            "power_watts": power_watts,
        }

    except ImportError:
        return {**_UNAVAILABLE, "reason": "pynvml_not_installed"}
    except Exception as exc:
        logger.debug("gpu_collector.failed error=%s", exc)
        return {**_UNAVAILABLE, "reason": str(exc)[:128]}
