# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The AS as a router the door mounts (#166: "expose the AS as a router"). `serve --tls`, the
listener and §2's loopback check are a3-doorman's; this module only turns HTTP into the calls the
request/response modules already answer, and back.

Mounted at the origin root, outside `rest.md` §1's `/v1/` prefix, with no authentication in front
of it: §6's document is unauthenticated, and a public client presents no credential at `/token`
(§1). The paths are `metadata`'s.

Served here:

- `GET /.well-known/oauth-authorization-server`: `metadata.document(issuer)`, built once.
- `POST /token`: `token_endpoint.respond`. The body is read up to `MAX_BODY_BYTES` and decoded as
  `application/x-www-form-urlencoded` pairs, in order. A body over the cap, or one that does not
  decode (not ASCII, a percent-escape that is not UTF-8, more than `MAX_FIELDS` pairs), is
  `invalid_request` before anything is read or spent. `owner` is the router's argument, the
  container's identity, never request input (#216's review). If `respond` or the store under it
  raises, the answer is `SERVER_ERROR`, still under `token_endpoint.HEADERS` (RFC 6749 §5.1), and
  never the framework's default 500, which carries no `Cache-Control: no-store`.

Not served yet, each held on a question this build does not answer by guessing:

- `/authorize`, `/login`, `/device`: §11.0's throttle runs first on their surfaces, and its
  release and window key wait on #208. `/authorize` also waits on #234 (the redirect query), and
  `/device`'s POST on #249 item 4.
- `/device_authorization`: #253 (an unregistered `client_id`'s answer, and so whether the registry
  read is padded).
- `/revoke`: #249 item 5 (whether RFC 7009 calls count against the `revoke` surface). It is
  mounted inside `budget.Budget` when it lands (§9.2).

§6 says the AS MUST NOT advertise an endpoint it does not implement, and the document names all
four. `HELD` lists the advertised paths not yet served, each with its hold, and `router`, the one
entry the door mounts, refuses to build while `HELD` is non-empty. A test checks `HELD` against the
routes actually built, so lifting a hold means serving the path and deleting its entry together.

The issuer is checked for shape only. Whether plain `http` may be served is §2's loopback rule
([0.3 · 9]), decided by the door's bind check from the socket, never here and never from the
issuer string.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from types import MappingProxyType
from urllib.parse import parse_qsl, urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from egzos.authz import AuditLedger, metadata, token_endpoint
from egzos.authz.tokens import TokenState

METADATA_PATH = "/.well-known/oauth-authorization-server"

#: A token request is a handful of short parameters. Anything larger is refused unread past the cap.
MAX_BODY_BYTES = 8192
#: More pairs than any grant names, and a bound on what `parse_qsl` builds.
MAX_FIELDS = 32

#: Advertised by §6 and not served yet, each path with the question it is held on.
HELD: Mapping[str, str] = MappingProxyType(
    {
        metadata.AUTHORIZE_PATH: "#208 throttle, #234 redirect query",
        metadata.DEVICE_AUTHORIZATION_PATH: "#253 unknown-client answer",
        metadata.REVOCATION_PATH: "#249 item 5 throttle surface",
    }
)

_INVALID_REQUEST = token_endpoint.Answer(400, {"error": "invalid_request"})
#: The answer when the work under `/token` raises. It names no cause.
SERVER_ERROR = token_endpoint.Answer(500, {"error": "server_error"})

_log = logging.getLogger(__name__)


def _issuer(issuer: str) -> str:
    """RFC 8414 §2: an `https` or `http` origin with a host, an optional numeric port, and no
    userinfo, path, query or fragment. The shape only: whether `http` may be served is the door's
    bind check (§2, [0.3 · 9])."""
    if not isinstance(issuer, str):
        raise TypeError("issuer must be a string")
    parts = urlsplit(issuer)
    try:
        port = parts.port  # raises for a port that is not a number in 0..65535
    except ValueError:
        raise ValueError("issuer's port must be a number") from None
    if (
        parts.scheme not in ("https", "http")
        or not parts.hostname
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
        or "@" in parts.netloc
        or port == 0
        or parts.netloc.endswith(":")  # an empty port
    ):
        raise ValueError("issuer must be an origin: scheme, host and port only")
    return issuer.rstrip("/")


async def _body(request: Request) -> bytes | None:
    """The request body, or None once it passes `MAX_BODY_BYTES`."""
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def _pairs(body: bytes) -> list[tuple[str, str]] | None:
    """The form's decoded pairs in order, a blank value kept so `token_endpoint` sees a repeat;
    None when the body does not decode."""
    try:
        text = body.decode("ascii")
        return parse_qsl(
            text,
            keep_blank_values=True,
            encoding="utf-8",
            errors="strict",
            max_num_fields=MAX_FIELDS,
        )
    except ValueError:  # UnicodeDecodeError included
        return None


def _send(answer: token_endpoint.Answer) -> JSONResponse:
    return JSONResponse(answer.body, status_code=answer.status, headers=token_endpoint.HEADERS)


def router(*, state: TokenState, ledger: AuditLedger, issuer: str, owner: str) -> APIRouter:
    """The AS's routes for a container at origin `issuer`, owned by `owner`: the entry the door
    mounts. Refuses to build while §6's document advertises a path in `HELD`."""
    if HELD:
        raise RuntimeError("the AS advertises endpoints it does not serve yet: " + ", ".join(HELD))
    return _build(state=state, ledger=ledger, issuer=issuer, owner=owner)


def _build(*, state: TokenState, ledger: AuditLedger, issuer: str, owner: str) -> APIRouter:
    """The routes served so far, with no `HELD` check; `router` is the mount entry."""
    document = metadata.document(_issuer(issuer))
    routes = APIRouter()

    @routes.get(METADATA_PATH, include_in_schema=False)
    def discover() -> JSONResponse:
        return JSONResponse(document)

    @routes.post(metadata.TOKEN_PATH, include_in_schema=False)
    async def token(request: Request) -> JSONResponse:
        body = await _body(request)
        params = _pairs(body) if body is not None else None
        if params is None:
            return _send(_INVALID_REQUEST)
        try:
            answer = await run_in_threadpool(
                token_endpoint.respond,
                state,
                ledger,
                params,
                content_type=request.headers.get("content-type"),
                authorization=request.headers.get("authorization"),
                owner=owner,
            )
        except Exception:  # any failure: one no-store answer that names no cause
            _log.exception("the token endpoint raised")
            answer = SERVER_ERROR
        return _send(answer)

    return routes
