from dataclasses import dataclass


TERMINAL_STATES = {"completed", "failed", "cancelled"}

TRANSITION_RULES: dict[str, set[str]] = {
    "received": {"queued", "failed", "cancelled"},
    "queued": {"scheduled", "failed", "cancelled"},
    "scheduled": {"executing", "failed", "cancelled"},
    "executing": {"fallback_executing", "completed", "failed", "cancelled"},
    "fallback_executing": {"completed", "failed", "cancelled"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}


@dataclass(frozen=True)
class TransitionValidation:
    allowed: bool
    reason: str | None = None


def validate_transition(current_state: str | None, next_state: str) -> TransitionValidation:
    if not next_state:
        return TransitionValidation(False, "target_state_missing")

    if current_state is None:
        return TransitionValidation(True)

    if current_state == next_state:
        return TransitionValidation(True)

    allowed_next = TRANSITION_RULES.get(current_state)
    if allowed_next is None:
        return TransitionValidation(False, f"unknown_current_state:{current_state}")

    if next_state not in allowed_next:
        if current_state in TERMINAL_STATES:
            return TransitionValidation(False, f"terminal_state:{current_state}")
        return TransitionValidation(False, f"invalid_transition:{current_state}->{next_state}")

    return TransitionValidation(True)

