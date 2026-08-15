"""Async-safe request and workspace context."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator

DEFAULT_WORKSPACE_ID = "default"
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_workspace_id: ContextVar[str] = ContextVar(
    "workspace_id", default=DEFAULT_WORKSPACE_ID
)
_api_key_id: ContextVar[str | None] = ContextVar("api_key_id", default=None)


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str | None
    workspace_id: str
    api_key_id: str | None


def get_request_context() -> RequestContext:
    return RequestContext(_request_id.get(), _workspace_id.get(), _api_key_id.get())


@contextmanager
def bind_request_context(
    *, request_id: str, workspace_id: str | None = None, api_key_id: str | None = None
) -> Iterator[RequestContext]:
    request_token = _request_id.set(request_id)
    workspace_token = _workspace_id.set(workspace_id or DEFAULT_WORKSPACE_ID)
    key_token = _api_key_id.set(api_key_id)
    try:
        yield get_request_context()
    finally:
        _api_key_id.reset(key_token)
        _workspace_id.reset(workspace_token)
        _request_id.reset(request_token)
