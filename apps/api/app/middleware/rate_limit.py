import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import get_settings

settings = get_settings()


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after: int
    reset_after: int


class RateLimitBuckets:
    """Deterministic fixed-window buckets keyed by workspace and API key."""

    def __init__(self, window_seconds: int = 60) -> None:
        self.window_seconds = window_seconds
        self._buckets: dict[tuple[str, str, int], int] = defaultdict(int)

    def check(
        self,
        workspace_id: str,
        api_key_id: str,
        *,
        limit: int,
        now: float | None = None,
    ) -> RateLimitDecision:
        current = time.time() if now is None else now
        window = int(current // self.window_seconds)
        key = (workspace_id, api_key_id, window)
        count = self._buckets[key]
        reset_after = self.window_seconds - int(current % self.window_seconds)
        if count >= limit:
            return RateLimitDecision(False, 0, reset_after, reset_after)
        self._buckets[key] = count + 1
        return RateLimitDecision(
            True,
            max(limit - count - 1, 0),
            0,
            reset_after,
        )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforce local fixed-window limits by workspace and API-key identity.

    The raw key is never retained: the middleware uses the authenticated key
    object when available and otherwise hashes the ``X-API-Key`` header. The
    configured per-key limit remains authoritative after authentication;
    anonymous requests retain the historical default limit.
    """

    def __init__(self, app: Any, default_rate_limit: int = 60) -> None:
        """Initialize the rate limiter.

        Args:
            app: The ASGI application to wrap.
            default_rate_limit: Default requests per minute when no key is found.
        """
        super().__init__(app)
        self._default_rate_limit = default_rate_limit
        self._buckets = RateLimitBuckets()

    async def dispatch(
        self, request: Request, call_next: Callable[..., Awaitable[Response]]
    ) -> Response:
        """Process the request through the rate limiter.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or endpoint handler.

        Returns:
            The response from the next handler, or a 429 if rate limited.
        """
        if not settings.RATE_LIMIT_ENABLED or settings.APP_ENV == "testing":
            return await call_next(request)

        api_key_id = self._get_key_identifier(request)
        workspace_id = request.headers.get("X-Workspace-ID", "default")
        rate_limit = self._get_rate_limit(request)

        decision = self._buckets.check(workspace_id, api_key_id, limit=rate_limit)
        if not decision.allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after": decision.retry_after,
                },
                headers={
                    "Retry-After": str(max(decision.retry_after, 1)),
                    "X-RateLimit-Limit": str(rate_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(decision.reset_after),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(rate_limit)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        response.headers["X-RateLimit-Reset"] = str(decision.reset_after)
        return response

    def _get_key_identifier(self, request: Request) -> str:
        """Extract a unique identifier for rate limiting from the request.

        Args:
            request: The incoming HTTP request.

        Returns:
            A string identifier (API key ID, IP, or 'anonymous').
        """
        api_key = getattr(request.state, "api_key", None)
        if api_key is not None:
            return str(api_key.id)
        if raw_key := request.headers.get("X-API-Key"):
            return f"key:{hashlib.sha256(raw_key.encode()).hexdigest()}"
        return f"ip:{request.client.host if request.client else 'anonymous'}"

    def _get_rate_limit(self, request: Request) -> int:
        """Get the rate limit for the current request's API key.

        Args:
            request: The incoming HTTP request.

        Returns:
            The configured requests-per-minute limit.
        """
        api_key = getattr(request.state, "api_key", None)
        if api_key is not None:
            return getattr(api_key, "rate_limit", self._default_rate_limit)
        return self._default_rate_limit
