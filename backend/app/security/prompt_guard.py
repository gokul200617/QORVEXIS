"""Prompt injection and prompt security guard.

Detects and blocks:
- Prompt injection attempts
- System prompt extraction
- Secret/credential extraction requests
- Instruction override attempts
"""

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger("qorvexis.security.prompt_guard")


# ── Regex patterns ─────────────────────────────────────────────────────────────

_INJECTION_PATTERNS: list[tuple[str, str]] = [
    # Instruction overrides
    (r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+instructions?", "instruction_override"),
    (r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions?", "instruction_override"),
    (r"forget\s+(everything|all)\s+(you('ve|\s+have)\s+been\s+told)", "instruction_override"),
    (r"you\s+are\s+now\s+(a\s+)?(?!a\s+helpful).{0,60}", "role_override"),
    (r"act\s+as\s+(if\s+you\s+are|a\s+new|a\s+different|an?\s+unrestricted)", "role_override"),
    (r"(pretend|simulate|roleplay)\s+(you\s+are|that\s+you)", "role_override"),
    (r"DAN\s*(mode|prompt|jailbreak)?", "jailbreak"),
    (r"jailbreak", "jailbreak"),
    # System prompt extraction
    (r"(show|print|reveal|tell me|what (is|are))\s+(your\s+)?(system\s+prompt|initial\s+instructions?|system\s+message)", "system_prompt_extraction"),
    (r"(what|tell me).{0,20}system.{0,20}prompt", "system_prompt_extraction"),
    (r"(show|display|output|print|what.{0,10}is).{0,20}(system|initial).{0,20}(prompt|instruction|message)", "system_prompt_extraction"),
    (r"repeat\s+(everything|all)\s+(above|before|in\s+your\s+system)", "system_prompt_extraction"),
    (r"output\s+(your\s+)?(system|initial)\s+(prompt|instructions?|message)", "system_prompt_extraction"),
    # Secret/credential extraction
    (r"(show|print|reveal|give me)\s+(the\s+)?(api\s+key|secret|password|credential|token)", "secret_extraction"),
    (r"(what\s+is|tell\s+me)\s+(the\s+)?(api\s+key|secret|password|credential)", "secret_extraction"),
    (r"leak\s+(the\s+)?(api\s+key|credential|secret|password)", "secret_extraction"),
    # Tenant data extraction
    (r"(show|list|dump|print)\s+(all\s+)?(users?|organizations?|tenants?|customers?)\s+(data|records?|information)", "tenant_data_extraction"),
    (r"(access|query|fetch)\s+(other|another|different)\s+(org|organization|tenant|user)", "tenant_data_extraction"),
]

_COMPILED = [(re.compile(pat, re.IGNORECASE), category) for pat, category in _INJECTION_PATTERNS]

# Maximum prompt length to prevent resource exhaustion
_MAX_PROMPT_LENGTH = 32_000


@dataclass
class PromptGuardResult:
    allowed: bool
    category: str | None = None
    reason: str | None = None


def check_prompt(text: str) -> PromptGuardResult:
    """Analyse a prompt for injection/extraction attempts.
    
    Returns PromptGuardResult(allowed=True) if safe.
    Returns PromptGuardResult(allowed=False, category=...) if blocked.
    """
    if not text:
        return PromptGuardResult(allowed=True)

    if len(text) > _MAX_PROMPT_LENGTH:
        logger.warning("prompt_guard.blocked reason=length_exceeded length=%d", len(text))
        return PromptGuardResult(
            allowed=False,
            category="length_exceeded",
            reason=f"Prompt exceeds maximum allowed length of {_MAX_PROMPT_LENGTH} characters.",
        )

    for pattern, category in _COMPILED:
        if pattern.search(text):
            logger.warning("prompt_guard.blocked reason=%s", category)
            return PromptGuardResult(
                allowed=False,
                category=category,
                reason=f"Request blocked: detected {category.replace('_', ' ')} pattern.",
            )

    return PromptGuardResult(allowed=True)
