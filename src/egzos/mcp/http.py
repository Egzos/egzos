# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
MCP over Streamable HTTP at the REST door's `/mcp` (identity.md §7): how an agent that is not on
the user's machine reaches the container. The transport is the MCP SDK's (buy, don't build).

The door resolves the bearer before a request gets here (rest.md §2, identity.md §3–§4): one
credential position, one throttle, one `401`. Every tool call in the request runs as that verified
caller, through the tools stdio serves (`egzos.mcp.server`), so coverage, silence and audit are
theirs. An agent's provider token is its registration intersected with its user's grant, and its
entries name the user it acts for.

- **Stateless, with JSON responses.** Each POST is its own exchange and no `Mcp-Session-Id` is
  issued, so there is no session another principal could present. GET and DELETE, which only a
  session needs, never reach the SDK: the door answers a verified one with the transport's `405`
  (identity.md §7). `subscriptions/listen` is not served either, so no POST becomes a stream that
  outlives the check of the caller who opened it.
- **The door's body limit**, not the SDK's larger default: what `/mcp` reads is what `/v1/` reads.
  Past the credential, the SDK's own answers (its JSON-RPC errors, and the bare `400`, `406` and
  `413` it gives a request it will not read) are the transport's, and turn on the request alone
  (identity.md §7).
- **The SDK's DNS-rebinding guard is off.** It would refuse every Host but loopback, and no
  contract names a Host. A rebound page has no credential to present: the door reads only
  `Authorization: Bearer`, never a cookie (rest.md §2 items 1 and 3), and its Origin policy is
  identity.md §6's CORS, which the door applies here as on every answer, preflight included.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from contextvars import ContextVar
from typing import TYPE_CHECKING

from starlette.types import Receive, Scope, Send

from egzos.container import Container
from egzos.mcp.server import build
from egzos.model import Token

if TYPE_CHECKING:
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

#: The verified caller of the request being served. The SDK carries a request's context into the
#: tool call it makes, so this is who every call in that request runs as.
_caller: ContextVar[Token | None] = ContextVar("egzos_mcp_caller", default=None)


class StreamableHttp:
    """The ASGI app the door routes `POST /mcp` to, behind its credential and its throttle."""

    def __init__(self, container: Container, *, max_body: int):
        # WARNING keeps the SDK's per-request INFO lines quiet; the SDK also installs a root log
        # handler when it builds a server, as it does for stdio.
        self.server = build(container, _caller.get, log_level="WARNING", subscriptions=False)
        self.max_body = max_body
        self._manager: StreamableHTTPSessionManager | None = None

    @contextlib.asynccontextmanager
    async def running(self) -> AsyncIterator[None]:
        """Serve for one lifespan of the door. The SDK runs a session manager only once, so each
        lifespan builds its own."""
        from mcp.server.transport_security import TransportSecuritySettings

        # Called for its side effect: the SDK creates `session_manager` here. The Starlette app
        # it returns is not mounted; the door routes `/mcp` to this object instead.
        self.server.streamable_http_app(
            stateless_http=True,
            json_response=True,
            max_request_body_size=self.max_body,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
        manager = self.server.session_manager
        async with manager.run():
            self._manager = manager
            try:
                yield
            finally:
                self._manager = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._manager is None:
            raise RuntimeError("the MCP door is not running")
        # The door put the caller it verified on the request (`request.state.token`); a request
        # that reached here without one runs as nobody, and every tool answers `NOT_LIVE`.
        reset = _caller.set(scope.get("state", {}).get("token"))
        try:
            await self._manager.handle_request(scope, receive, send)
        finally:
            _caller.reset(reset)
