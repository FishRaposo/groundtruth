import time
from collections import defaultdict
from typing import Any, Callable, Awaitable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import get_settings

settings = get_settings()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that enforces per-key rate limiting using a sliding window.

    Tracks request timestamps per API key in memory. When the number of
    requests within the sliding window exceeds the key's configured limit,
    a 429 response is returned with a Retry-After header.
    """

    def __init__(self, app: Any, default_rate_limit: int = 60) -> None:
        """Initialize the rate limiter.

        Args:
            app: The ASGI application to wrap.
            default_rate_limit: Default requests per minute when no key is found.
        """
        super().__init__(app)
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._default_rate_limit = default_rate_limit
        self._request_count = 0

    async def dispatch(self, request: Request, call_next: Callable[..., Awaitable[Response]]) -> Response:
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
        rate_limit = self._get_rate_limit(request)

        now = time.time()
        window_start = now - 60.0

        self._cleanup_old_entries(api_key_id, window_start)

        recent = [ts for ts in self._requests[api_key_id] if ts > window_start]
        self._requests[api_key_id] = recent

        if len(recent) >= rate_limit:
            oldest_in_window = min(recent)
            retry_after = int(oldest_in_window + 60.0 - now) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded", "retry_after": retry_after},
                headers={"Retry-After": str(max(retry_after, 1))},
            )

        self._requests[api_key_id].append(now)
        self._request_count += 1

        if self._request_count % 100 == 0:
            self._periodic_cleanup()

        response = await call_next(request)
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

    def _cleanup_old_entries(self, key: str, window_start: float) -> None:
        """Remove timestamps outside the sliding window for a given key.

        Args:
            key: The rate limit key to clean up.
            window_start: The earliest timestamp to keep.
        """
        self._requests[key] = [ts for ts in self._requests[key] if ts > window_start]

    def _periodic_cleanup(self) -> None:
        """Remove stale entries across all keys to prevent memory leaks."""
        now = time.time()
        window_start = now - 120.0
        stale_keys = [
            k for k, timestamps in self._requests.items()
            if not any(ts > window_start for ts in timestamps)
        ]
        for k in stale_keys:
            del self._requests[k]
