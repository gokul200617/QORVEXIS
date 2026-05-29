"""Workload signature generation.

Creates a deterministic, repeatable fingerprint for any prompt/workload.
Powers duplicate detection and cache opportunity analytics.
"""

import hashlib
import re


def _normalize_text(text: str) -> str:
    """Normalize text to reduce superficial variance.

    - Lowercases
    - Strips leading/trailing whitespace
    - Collapses internal whitespace to single spaces
    - Removes common filler punctuation
    """
    text = text.lower().strip()
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    # Remove punctuation that doesn't change semantic meaning
    text = re.sub(r"[!?.,:;\"']+", "", text)
    return text


def generate_signature(text: str) -> str:
    """Generate a short workload signature for the given text.

    Returns an 8-character hex string (32-bit collision space).
    Suitable for duplicate detection at operational scale.
    """
    normalized = _normalize_text(text)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return digest[:8]


def generate_full_signature(text: str) -> str:
    """Full 16-character hex signature for higher-fidelity matching."""
    normalized = _normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
