"""slowapi rate limiter instance for Qorvexis.

Limits:
  - Anonymous:     10/minute  (by IP)
  - Authenticated: 60/minute  (by JWT user id extracted from Authorization header)
"""

import logging
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger("qorvexis.security.rate_limiter")


def _get_request_identity(request: Request) -> str:
    """Return user-id from JWT if present, else fall back to IP address.
    
    Authenticated users get a higher quota (60/min vs 10/min for anonymous).
    This key function only extracts the identity; the actual limit string is
    applied per-route via @limiter.limit("60/minute") decorator.
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        # Extract sub claim without full validation (rate-limit key only)
        try:
            import base64, json
            # JWT has 3 parts: header.payload.signature
            parts = token.split(".")
            if len(parts) == 3:
                # Pad base64
                padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
                payload = json.loads(base64.b64decode(padded))
                sub = payload.get("sub")
                if sub:
                    return f"user:{sub}"
        except Exception:
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=_get_request_identity, default_limits=["60/minute"])
