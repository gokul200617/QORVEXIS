"""Pure normalization utility functions.

These functions perform no I/O and have no external dependencies — they
are safe to import anywhere without import cycles.
"""

from __future__ import annotations


def safe_divide(numerator: float | None, denominator: float | None, default: float = 0.0) -> float:
    """Divide without raising ZeroDivisionError."""
    if numerator is None or denominator is None or denominator == 0:
        return default
    return numerator / denominator


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    """Clamp a value to [low, high]."""
    return max(low, min(high, value))


def pct(part: float | None, total: float | None) -> float:
    """Calculate percentage, returns 0.0 if inputs are invalid."""
    return round(clamp(safe_divide(part, total) * 100), 2)


def safe_float(value: object, default: float = 0.0) -> float:
    """Coerce any value to float safely."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def safe_int(value: object, default: int = 0) -> int:
    """Coerce any value to int safely."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def efficiency_score(used: float | None, capacity: float | None) -> float:
    """Return 0–100 efficiency: how well capacity is being utilized."""
    ratio = safe_divide(used, capacity)
    return round(clamp(ratio * 100), 2)


def waste_score(idle_pct: float | None) -> float:
    """Return 0–100 waste score based on idle percentage."""
    return round(clamp(safe_float(idle_pct)), 2)
