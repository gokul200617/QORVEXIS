"""System metrics collector — uses psutil for local infrastructure telemetry."""

import logging
import platform

logger = logging.getLogger("qorvexis.telemetry.system")


def collect_system_metrics() -> dict:
    """Collect a single non-blocking snapshot of local system metrics.

    Returns a dict with available fields. On partial failure, fields that
    could not be read are omitted rather than raising.
    """
    result: dict = {}

    try:
        import psutil  # noqa: PLC0415

        # CPU — non-blocking (interval=None uses last cached value)
        try:
            result["cpu_percent"] = psutil.cpu_percent(interval=None)
        except Exception as exc:
            logger.debug("system_collector.cpu_failed error=%s", exc)

        # Memory
        try:
            vm = psutil.virtual_memory()
            result["memory_percent"] = vm.percent
            result["memory_total_bytes"] = vm.total
            result["memory_available_bytes"] = vm.available
        except Exception as exc:
            logger.debug("system_collector.memory_failed error=%s", exc)

        # Disk (root partition)
        try:
            disk = psutil.disk_usage("/")
            result["disk_percent"] = disk.percent
            result["disk_total_bytes"] = disk.total
            result["disk_free_bytes"] = disk.free
        except Exception:
            # Windows may need a drive letter
            try:
                disk = psutil.disk_usage("C:\\")
                result["disk_percent"] = disk.percent
                result["disk_total_bytes"] = disk.total
                result["disk_free_bytes"] = disk.free
            except Exception as exc:
                logger.debug("system_collector.disk_failed error=%s", exc)

        # Load average (Unix only — skip silently on Windows)
        try:
            load = psutil.getloadavg()
            result["load_avg_1m"] = round(load[0], 2)
            result["load_avg_5m"] = round(load[1], 2)
            result["load_avg_15m"] = round(load[2], 2)
        except (AttributeError, OSError):
            pass  # Not available on Windows

    except ImportError:
        logger.warning("system_collector.psutil_unavailable")

    result["platform"] = platform.system()
    result["python_version"] = platform.python_version()

    return result
