"""Finish in-flight database reads/cleanup before rethrowing cancellation.

Cancelling a driver between execute and fetch can retain a native SQLite cursor
and block the transaction that records an interrupted query. These boundaries
drain reads and query finalization, never model inference or provider requests.
"""

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

import anyio

T = TypeVar("T")


async def complete_read(operation: Awaitable[T]) -> T:
    return await _complete(operation)


async def complete_cleanup(operation: Awaitable[T]) -> T:
    """Finish query finalization even when its caller is directly cancelled."""
    return await _complete(operation)


async def _complete(operation: Awaitable[T]) -> T:
    pending = asyncio.ensure_future(operation)
    try:
        return await asyncio.shield(pending)
    except asyncio.CancelledError:
        # AnyIO cancellation is level-triggered; direct asyncio cancellation may
        # also arrive repeatedly. The session stays exclusively owned until its
        # read finishes, so rollback cannot race an unfinished driver operation.
        with anyio.CancelScope(shield=True):
            while not pending.done():
                try:
                    await asyncio.shield(pending)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not pending.cancelled():
                pending.exception()  # Observe a failed read without masking cancel.
        raise
