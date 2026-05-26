from app.services.failover_manager import failover_manager
from app.services.provider_scorer import provider_scorer


def simulate_provider_outage(provider: str, failures: int = 3) -> dict:
    for _ in range(failures):
        provider_scorer.record_failure(provider)
        failover_manager.record_failure(provider)
    return {
        "provider": provider,
        "failures_injected": failures,
        "failover": failover_manager.snapshot(),
        "scores": provider_scorer.get_all_scores(),
    }

