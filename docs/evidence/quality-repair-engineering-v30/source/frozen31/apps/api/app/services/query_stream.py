"""Own connected query finalization across transport and generator boundaries."""

from collections.abc import AsyncGenerator, Awaitable, Callable

import anyio
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from app.db.cancellation import complete_cleanup


class QueryStreamingResponse(StreamingResponse):
    def __init__(
        self,
        content: AsyncGenerator[str, None],
        finalize: Callable[[], Awaitable[None]],
    ) -> None:
        super().__init__(content, media_type="text/event-stream")
        self._query_content = content
        self._finalize_query = finalize

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # ASGI2.4 send errors can abandon an iterator at yield, without
            # throwing into it. Close explicitly before the DB dependency exits.
            with anyio.CancelScope(shield=True):
                await complete_cleanup(self._close_query())

    async def _close_query(self) -> None:
        try:
            await self._query_content.aclose()
        finally:
            await self._finalize_query()
