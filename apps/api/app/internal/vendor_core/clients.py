# Vendored from FishRaposo/operator-shared-core v1.3.0.
# Source commit: dbf276a7708da65b55e1f10b35af634b300d1f07.
import asyncio
from typing import Any, Optional

import httpx
from loguru import logger

from app.internal.vendor_core.logging import correlation_id_var


class BaseHTTPClient:
    """Base HTTP client using httpx.AsyncClient.

    Handles retries, timeouts, and correlation ID forwarding.
    """

    def __init__(
        self,
        base_url: str = "",
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def close(self) -> None:
        """Close the underlying client connection pool."""
        await self.client.aclose()

    async def request(
        self,
        method: str,
        url: str,
        headers: Optional[dict[str, str]] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Performs HTTP request with correlation ID forwarding and retries."""
        headers = headers or {}

        # Forward correlation ID if set in current context
        corr_id = correlation_id_var.get()
        if corr_id and "X-Correlation-ID" not in headers:
            headers["X-Correlation-ID"] = corr_id

        attempt = 0
        while True:
            try:
                attempt += 1
                logger.debug(
                    f"HTTP Request: {method} {url} - "
                    f"Attempt {attempt}/{self.max_retries}"
                )
                response = await self.client.request(
                    method, url, headers=headers, **kwargs
                )

                # Check for 5xx status codes to trigger retry
                if response.status_code >= 500 and attempt < self.max_retries:
                    logger.warning(
                        f"HTTP {response.status_code} received from server. Retrying..."
                    )
                else:
                    response.raise_for_status()
                    return response
            except (httpx.HTTPError, httpx.RequestError) as exc:
                if attempt >= self.max_retries:
                    logger.error(
                        f"HTTP Request failed after {attempt} attempts: "
                        f"{method} {url} - Error: {str(exc)}"
                    )
                    raise exc

            # Exponential backoff sleep
            sleep_time = self.backoff_factor * (2 ** (attempt - 1))
            await asyncio.sleep(sleep_time)

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("DELETE", url, **kwargs)
