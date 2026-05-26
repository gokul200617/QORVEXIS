from app.services.inference_service import classify_request, select_provider_name

PRIORITY_WEIGHTS = {
    "critical": 0,
    "high": 1,
    "normal": 2,
    "low": 3,
}

LOW_PRIORITY_KEYWORDS = ("summarize", "summary", "overview", "brief", "rewrite")


def assign_priority(prompt: str) -> str:
    normalized = prompt.lower()
    category = classify_request(prompt)

    if any(word in normalized for word in ("outage", "production down", "sev1", "critical")):
        return "critical"
    if category in {"debugging", "infrastructure"}:
        return "high"
    if any(word in normalized for word in LOW_PRIORITY_KEYWORDS):
        return "low"
    return "normal"


def priority_weight(priority: str) -> int:
    return PRIORITY_WEIGHTS.get(priority, PRIORITY_WEIGHTS["normal"])


def select_execution_provider(prompt: str) -> str:
    return select_provider_name(prompt)


# ---------------------------------------------------------------------------
# Phase 5 — Adaptive scheduling extensions
# ---------------------------------------------------------------------------

def select_adaptive_provider(prompt: str) -> str:
    """Provider selection enhanced with failover cooldown and scoring awareness.

    Falls back to the alternate provider when the preferred one is in cooldown.
    When neither is cooled down, prefers the higher-scored provider only if the
    score gap is significant (>10 points) and keyword routing did not produce
    a strong preference.
    """
    from app.services.failover_manager import failover_manager
    from app.services.provider_scorer import provider_scorer

    preferred = select_provider_name(prompt)
    fallback = "gemini" if preferred == "groq" else "groq"

    # Cooldown check — hard override
    best = failover_manager.get_best_provider(preferred, fallback)
    if best != preferred:
        return best

    # Scoring influence — soft override (only when gap is significant)
    pref_score = provider_scorer.get_score(preferred)
    fall_score = provider_scorer.get_score(fallback)
    if fall_score - pref_score > 10:
        return fallback

    return preferred


def boost_stale_priority(base_priority: str, queue_wait_ms: int) -> str:
    """Starvation prevention: boost priority if request has waited too long.

    If a low-priority request has been waiting >30s, bump to normal.
    If a normal-priority request has been waiting >60s, bump to high.
    """
    if base_priority == "low" and queue_wait_ms > 30_000:
        return "normal"
    if base_priority == "normal" and queue_wait_ms > 60_000:
        return "high"
    return base_priority

