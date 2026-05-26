from dataclasses import dataclass
import logging
from time import perf_counter

from app.providers import GeminiProvider, GroqProvider, InferenceProvider, ProviderError
from app.services.cost_tracker import cost_tracker
from app.services.failover_manager import failover_manager
from app.services.provider_scorer import provider_scorer

logger = logging.getLogger("qorvexis.inference")

GROQ_ROUTING_KEYWORDS = (
    "algorithm",
    "api error",
    "async",
    "bug",
    "build failed",
    "class ",
    "code",
    "compile",
    "crash",
    "debug",
    "dependency",
    "exception",
    "failed",
    "fix",
    "function",
    "github",
    "importerror",
    "indexerror",
    "javascript",
    "json",
    "keyerror",
    "leetcode",
    "log",
    "module",
    "node",
    "npm",
    "package",
    "pip",
    "postgres",
    "program",
    "python",
    "query",
    "runtimeerror",
    "sql",
    "stack trace",
    "syntaxerror",
    "terminal",
    "traceback",
    "typeerror",
    "typescript",
    "undefined",
    "valueerror",
)

GROQ_ROUTING_PATTERNS = (
    "```",
    " at ",
    "error:",
    "errno",
    "line ",
    "localhost",
    "null",
    "undefined",
)

CATEGORY_KEYWORDS = {
    "debugging": (
        "bug",
        "crash",
        "debug",
        "error",
        "exception",
        "failed",
        "fix",
        "stack trace",
        "traceback",
        "typeerror",
        "valueerror",
    ),
    "coding": (
        "algorithm",
        "class ",
        "code",
        "function",
        "javascript",
        "leetcode",
        "program",
        "python",
        "typescript",
    ),
    "infrastructure": (
        "api",
        "database",
        "deploy",
        "infrastructure",
        "latency",
        "load balancer",
        "orchestration",
        "postgres",
        "provider",
        "server",
        "supabase",
    ),
    "reasoning": (
        "analyze",
        "compare",
        "decide",
        "explain why",
        "reason",
        "tradeoff",
        "why",
    ),
}


@dataclass(frozen=True)
class InferenceResult:
    provider: str
    original_provider: str
    fallback_used: bool
    model: str
    category: str
    response: str
    latency_ms: int


def classify_request(prompt: str) -> str:
    normalized_prompt = prompt.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in normalized_prompt for keyword in keywords):
            return category
    return "general"


def select_provider_name(prompt: str) -> str:
    normalized_prompt = prompt.lower()
    if any(keyword in normalized_prompt for keyword in GROQ_ROUTING_KEYWORDS):
        return "groq"

    if any(pattern in normalized_prompt for pattern in GROQ_ROUTING_PATTERNS):
        return "groq"

    return "gemini"


def get_fallback_provider_name(provider_name: str) -> str:
    return "gemini" if provider_name == "groq" else "groq"


def build_provider(provider_name: str) -> InferenceProvider:
    if provider_name == "groq":
        return GroqProvider()
    return GeminiProvider()


def execute_provider(provider_name: str, prompt: str) -> tuple[InferenceProvider, str]:
    provider = build_provider(provider_name)
    response = provider.generate_response(prompt)
    return provider, response


def build_memory_enriched_prompt(
    prompt: str,
    memory_context: list[dict[str, str]] | None,
) -> str:
    if not memory_context:
        return prompt

    context_blocks = []
    for index, entry in enumerate(memory_context, start=1):
        context_blocks.append(
            "\n".join(
                (
                    f"Context item {index}:",
                    f"Prior request: {entry['prompt']}",
                    f"Prior response: {entry['response']}",
                )
            )
        )

    return "\n\n".join(
        (
            "Qorvexis operational session memory follows. Use it only as "
            "continuity context for this infrastructure workload.",
            "\n\n".join(context_blocks),
            "Current request:",
            prompt,
        )
    )


def run_inference(
    prompt: str,
    memory_context: list[dict[str, str]] | None = None,
) -> InferenceResult:
    category = classify_request(prompt)
    provider_name = select_provider_name(prompt)
    fallback_provider_name = get_fallback_provider_name(provider_name)
    provider_prompt = build_memory_enriched_prompt(prompt, memory_context)
    started_at = perf_counter()

    logger.info(
        "inference.request.start category=%s selected_provider=%s fallback_provider=%s",
        category,
        provider_name,
        fallback_provider_name,
    )

    try:
        provider, response = execute_provider(provider_name, provider_prompt)
        fallback_used = False
        logger.info(
            "inference.provider.success provider=%s model=%s",
            provider.name,
            provider.model,
        )
    except ProviderError as primary_exc:
        provider_scorer.record_failure(provider_name)
        failover_manager.record_failure(provider_name)
        logger.warning(
            "inference.provider.failure provider=%s error=%s",
            provider_name,
            primary_exc,
        )
        try:
            provider, response = execute_provider(fallback_provider_name, provider_prompt)
            fallback_used = True
            logger.warning(
                "inference.failover.success original_provider=%s fallback_provider=%s",
                provider_name,
                provider.name,
            )
        except ProviderError as fallback_exc:
            provider_scorer.record_failure(fallback_provider_name)
            failover_manager.record_failure(fallback_provider_name)
            logger.error(
                "inference.failover.failure original_provider=%s fallback_provider=%s error=%s",
                provider_name,
                fallback_provider_name,
                fallback_exc,
            )
            raise ProviderError(
                "Primary and fallback providers failed. "
                f"primary={primary_exc}; fallback={fallback_exc}"
            ) from fallback_exc
    except Exception as exc:
        raise ProviderError(f"{provider_name} provider failed: {exc}") from exc

    latency_ms = round((perf_counter() - started_at) * 1000)

    # Phase 5 — record to operational intelligence systems
    provider_scorer.record_success(provider.name, latency_ms)
    failover_manager.record_success(provider.name)
    estimated_cost = cost_tracker.record_request(provider.name, prompt, response)

    logger.info(
        "inference.request.complete provider=%s original_provider=%s fallback_used=%s latency_ms=%s estimated_cost=%.6f",
        provider.name,
        provider_name,
        fallback_used,
        latency_ms,
        estimated_cost,
    )

    return InferenceResult(
        provider=provider.name,
        original_provider=provider_name,
        fallback_used=fallback_used,
        model=provider.model,
        category=category,
        response=response,
        latency_ms=latency_ms,
    )
