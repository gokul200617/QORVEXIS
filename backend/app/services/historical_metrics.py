import threading
import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.settings import settings


class HistoricalMetricsStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._series: dict[str, deque[dict[str, Any]]] = {}
        self._history_file = Path(settings.historical_metrics_file)
        self._load_history()

    def record(self, name: str, payload: dict[str, Any]) -> None:
        sample = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        with self._lock:
            if name not in self._series:
                self._series[name] = deque(maxlen=settings.historical_metrics_window)
            self._series[name].append(sample)
            self._append_sample(name, sample)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                name: list(samples)
                for name, samples in self._series.items()
            }

    def _load_history(self) -> None:
        if not self._history_file.exists():
            return
        try:
            lines = self._history_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for line in lines[-settings.historical_metrics_window * 4:]:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = record.get("name")
            sample = record.get("sample")
            if not isinstance(name, str) or not isinstance(sample, dict):
                continue
            if name not in self._series:
                self._series[name] = deque(maxlen=settings.historical_metrics_window)
            self._series[name].append(sample)

    def _append_sample(self, name: str, sample: dict[str, Any]) -> None:
        try:
            with self._history_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"name": name, "sample": sample}, sort_keys=True))
                handle.write("\n")
        except OSError:
            return


historical_metrics = HistoricalMetricsStore()
