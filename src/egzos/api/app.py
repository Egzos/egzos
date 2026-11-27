# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The REST door's routes (spec/contracts/rest.md §1–§4.1): who may call, the one refusal, CORS for
the browser origins, and the reads and writes that need no confirm.

Every request passes the door in one order: CORS preflight, the throttle (§2 item 7), the credential
(a container `Token` or a provider token, `identity.md` §3), then the route. Every answer is JSON
under the same three headers, and every refusal that turns on what exists or what the token may do
is §3's one `404`, byte for byte. Nothing here renders an item: a body is a JSON string, and data.

The acts the confirm gates (§4.2) — a move or copy that widens an audience, and approve, deny and
promote — answer in two legs on one route: the first issues a challenge and says who would newly
see the item, the second spends it with a proof, and the act lands in the same transaction. An
artifact arrives through an upload (§4.4): open, bytes, item, and leaves through a `BlobGrant`
(§6): `GET /v1/fetch` and `GET /v1/items/{id}` carry one beside an artifact whose bytes do not ride
inline, and `GET /v1/blobs/{sha256}` redeems it, by the descriptor alone, never a bearer. An admin
lists the grants, grants access with the confirm, and ends one (§4.3), with the confirm where it is
someone else's. A person lists the agents serving them, registers one with the confirm, ends one,
and reads what one did for them (§4.3): an admin ends one serving someone else with the confirm.
A person registers a terminal of theirs with the confirm, lists their terminals, live or ended,
ends one and reads what was done through it, as for an agent (§4.3); each family of routes reads
its own kind only. A terminal's token is its person, but it gives no one access and concludes no
confirm: the routes that give access refuse it before any leg (§4.3).

MCP over Streamable HTTP (identity.md §7) is `POST /mcp`, past the same credential and throttle:
its `401` alone names the protected-resource metadata, which is served to anyone, unthrottled.

A person tombstones an item (§4): at once, or with the confirm where a person promoted it; never an
agent.
"""

from __future__ import annotations

import asyncio
import calendar
import contextlib
import json
import re
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, Request
from starlette.responses import Response, StreamingResponse

from egzos._ids import is_ulid
from egzos._types import CONTRACT_VERSION, DoorFeature, StorageBusy
from egzos.api.blobs import PULL_HEADERS, redeem
from egzos.api.throttle import Throttle, throttle_key
from egzos.backends.base import malformed
from egzos.confirm import CREDENTIAL_NAME_MAX, REMOVE_REASONS, person_of, terminal_of
from egzos.container import Container
from egzos.identity import (
    GrantToken,
    LastAdmin,
    TooManyAgents,
    TooManyTerminals,
    display_name,
    principal_id,
    provider_id,
)
from egzos.ledger import attributed
from egzos.mcp.http import StreamableHttp
from egzos.model import CONTAINER_TYPES, KINDS, VERIFIED_ONLY_KINDS, ContextItem, Node, Token
from egzos.store.blobs import grant_url
from egzos.store.find import QueryError, find, parse, shown
from egzos.store.items import StoreError
from egzos.store.nodes import AmbiguousRef, StructureError, valid_name
from egzos.store.uploads import MAX_HELD, TooManyUploads, valid_open
from egzos.store.uploads import person_of as opener_of
from egzos.trust import HumanOnly, TrustError

#: §3: the four lines every answer of this door carries (Content-Type is the response's own).
HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
METHODS = "GET, POST, PUT, DELETE"
#: identity.md §6: the same CORS headers on every answer to an allowed origin, whatever it is.
CORS_ALLOW_HEADERS = "Authorization, Content-Type"
#: A request body larger than this is not one this door reads (the upload route has its own).
BODY_MAX_BYTES = 256 * 1024
#: How often the door closes throttle windows (§2 item 7's release and tally).
CLOSE_EVERY_SECONDS = 15

_CREATABLE = tuple(t for t in CONTAINER_TYPES if t not in ("inbox", "global", "uxo"))
#: §4.4: what `GET /v1/pending` says of an orphaned upload, beside its id.
ORPHAN_KEYS = ("name", "size", "sha256", "scope", "opened_at")
#: identity.md §7: MCP's endpoint, and where its protected-resource metadata (RFC 9728) lives.
MCP_PATH = "/mcp"
METADATA_PATH = "/.well-known/oauth-protected-resource"
#: rest.md §6: the one route no bearer is read on, for GET only.
PULL_PATH = re.compile(r"/v1/blobs/[^/]+")
#: rest.md §4.6: the words `GET /v1/limits` names, each only once its code runs here and every
#: condition §4.6 sets for it holds. `items.rename` and `scopes.rename` wait on their routes;
#: `grants.own` is named with the read it names, which lands after every rule it needs (§4.3).
FEATURES: tuple[DoorFeature, ...] = ("terminals.machine", "grants.own")


def _json(status: int, payload: Any, extra: dict[str, str] | None = None) -> Response:
    body = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode()
    return Response(body, status_code=status, media_type="application/json",
                    headers={**HEADERS, **(extra or {})})


def refusal() -> Response:
    """§3's one refusal: absent, uncovered, lacking the capability, unserved, undeclared."""
    return _json(404, {"error": "not_found"})


def unauthorized(metadata: str | None = None) -> Response:
    """§2 item 5: every unauthenticated case, byte-identical. At `/mcp` the challenge names the
    protected-resource metadata (identity.md §7); on `/v1/` it carries no parameter."""
    challenge = f'Bearer resource_metadata="{metadata}"' if metadata else "Bearer"
    return _json(401, {"error": "unauthorized"}, {"WWW-Authenticate": challenge})


def invalid() -> Response:
    """§3: a request that fails on a fact identical for every container."""
    return _json(400, {"error": "invalid_request"})


def busy() -> Response:
    """§3: the store raised `StorageBusy`, so nothing was written; it names nothing requested."""
    return _json(503, {"error": "busy"}, {"Retry-After": "1"})


def ambiguous(paths: list[str]) -> Response:
    return _json(409, {"error": "ambiguous", "matches": sorted(paths)})


class Invalid(Exception):
    """The request's shape is wrong: answered `400` before any lookup."""


def _only(params: Any, allowed: set[str]) -> None:
    if set(params) - allowed or any(len(params.getlist(k)) > 1 for k in params):
        raise Invalid


async def _bounded(request: Request, limit: int) -> bytes:
    """The request body, read only up to `limit` bytes: a declared or actual length beyond it is
    refused before the rest is read, so no caller makes the door hold a body it will not take."""
    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > limit):
        raise Invalid
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise Invalid
        chunks.append(chunk)
    return b"".join(chunks)


async def _exactly(request: Request, size: int) -> bytes | None:
    """An upload's bytes (rest.md §4.4 item 2): exactly `size` of them, or None. The door reads at
    most `size` bytes, and none at all when the declared length already says otherwise."""
    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) != size):
        return None
    chunks, got = [], 0
    async for chunk in request.stream():
        got += len(chunk)
        if got > size:
            return None
        chunks.append(chunk)
    return b"".join(chunks) if got == size else None


async def _object(request: Request, allowed: set[str], required: set[str]) -> dict[str, Any]:
    raw = await _bounded(request, BODY_MAX_BYTES)
    try:
        body = json.loads(raw)
    except ValueError as e:
        raise Invalid from e
    if not isinstance(body, dict) or set(body) - allowed or required - set(body) or malformed(body):
        raise Invalid  # U+0000 or ill-formed Unicode, in a key or a value at any depth (§3)
    return body


def _str(value: Any, *, optional: bool = False, limit: int = 1024) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value or len(value) > limit:
        raise Invalid
    return value


class Door:
    """The door over one container: the credential, the throttle and the routes' shared reads."""

    def __init__(self, container: Container, throttle: Throttle | None = None):
        self.c = container
        self.throttle = throttle or Throttle(
            container.backend, container.ledger, throttle_key(container.home),
            atomic=container.backend.atomic,
        )

    def origins(self) -> set[str]:
        return set((self.c.config_value("identity.browser_origins") or "").split())

    def caller(self, header: str | None) -> Token | None:
        """The live caller a bearer value proves, or None (`rest.md` §2): a container `Token`,
        else a provider token through all seven checks. Only the `Authorization` header is read."""
        if not header or not header.startswith("Bearer "):
            return None
        value = header[len("Bearer "):]
        if not value or value != value.strip():
            return None
        token = self.c.auth.use(value)
        if token is not None:
            return token
        return self.c.identity.verify(value)

    # -- shared reads ---------------------------------------------------------------------------
    def probe(self, token: Token, ref: str | None) -> None:
        """§4: a refusal appends a read, identical for every case."""
        self.c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                             client=token.client, ref=ref, items=[], layers=[], withheld=0)

    def start(self, token: Token) -> Node | None:
        """Where a scope defaults to: the token's first grant, or the personal root."""
        if token.scopes and token.scopes[0] != "*":
            node = self.c.backend.get_node(token.scopes[0])
            return node if node and self.c.trust.covers(token, node) else None
        return self.c.nodes.user_root()

    def scope(self, token: Token, ref: str | None) -> Node | None:
        """A covered node, or None for absent and uncovered alike. Raises `AmbiguousRef` to a
        token holding `fetch`: the matches are named only to one that could list them, and to
        any other an ambiguous tail is an absent one (§3)."""
        if ref is None:
            return self.start(token)
        try:
            node = self.c.nodes.resolve_ref(ref, token)
        except AmbiguousRef:
            if token.has("fetch"):
                raise
            return None
        return node if node and self.c.trust.covers(token, node) else None

    def node(self, node: Node) -> dict[str, Any]:
        return {**node.to_dict(), "path": self.c.nodes.path(node)}

    def entry(self, item: dict[str, Any], node: Node, shadowed_by: str | None = None) -> dict:
        return {"item": item, "layer": self.c.nodes.path(node), "layer_type": node.type,
                "shadowed_by": shadowed_by}

    def readable(self, token: Token, item, node: Node) -> bool:
        """Whether `GET /v1/items/{id}` serves the item to this token (§3's list)."""
        if item.status == "quarantined":
            return False
        if item.kind in VERIFIED_ONLY_KINDS and item.status != "verified":
            return False
        return token.has("fetch") and self.c.trust.covers(token, node) and shown(
            self.c, token, item, node
        )


def create_app(
    container: Container, *, door: Door | None = None, origin: str = "http://127.0.0.1:7426"
) -> FastAPI:
    """The door, served from `origin`: the door's own, as `serve` binds it (`bound_origin`). The
    default is `serve`'s default bind; only tests rely on it. Where `identity.origin` is set, that
    is the origin clients reach, and `/mcp`'s metadata and challenge name it (identity.md §2)."""
    d = door or Door(container)
    c = container
    own = origin  # the middleware's `origin` is the request's header
    mcp = StreamableHttp(container, max_body=BODY_MAX_BYTES)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        async def closer() -> None:
            while True:
                await asyncio.sleep(CLOSE_EVERY_SECONDS)
                with contextlib.suppress(Exception):  # a closer that fails tries next round
                    d.throttle.close()

        task = asyncio.create_task(closer())
        try:
            async with mcp.running():
                yield
        finally:
            task.cancel()

    def public() -> str:
        """The container's public origin (identity.md §2), read on every request so that a
        `config set` reaches a running door; absent, the origin `serve` binds."""
        named = c.config_value("identity.origin")
        return own if named is None else named

    def resource_metadata() -> Response:
        """RFC 9728's document for `/mcp` (identity.md §7): the public origin, and the provider that
        issues its tokens. A container with no provider has none to name (§1), so the key is left
        out, as RFC 9728 allows."""
        issuer = c.config_value("identity.issuer")
        doc: dict[str, Any] = {"resource": public()}
        if issuer is not None:
            doc["authorization_servers"] = [issuer]
        return _json(200, doc)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.middleware("http")
    async def the_door(request: Request, call_next):
        origin = request.headers.get("origin")
        cors: dict[str, str] = {}
        if origin is not None and origin in d.origins():
            cors = {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Headers": CORS_ALLOW_HEADERS,
                "Access-Control-Allow-Methods": METHODS,
                "Vary": "Origin",
            }

        def out(response: Response) -> Response:
            for key, value in HEADERS.items():  # §4.1's headers on MCP's answers too
                response.headers.setdefault(key, value)
            response.headers.update(cors)
            return response

        try:
            return await admit(request, call_next, out, cors)
        except StorageBusy:  # §3: the write lock was not taken in time, the token check's included
            return out(busy())
        except Exception:  # noqa: BLE001 — never a stack, a path or an exception's text
            return out(_json(500, {"error": "internal"}))

    async def admit(request: Request, call_next, out, cors: dict[str, str]) -> Response:
        """Past CORS: the preflight, the metadata, the throttle, the credential, then the route."""
        path = request.url.path
        if request.method == "OPTIONS":
            # identity.md §6: a preflight from an allowed origin gets 204 on every /v1/ path,
            # declared or not, and at /mcp; from any other origin, §3's refusal and no CORS header.
            if cors and (path.startswith("/v1/") or path == MCP_PATH):
                return out(Response(status_code=204, headers=HEADERS))
            return refusal()
        if path == METADATA_PATH:
            # Public and the same for every caller, so it needs no credential and is never held:
            # a client reads it to learn where to get one (identity.md §7).
            return out(resource_metadata() if request.method == "GET" else refusal())
        metadata = public() + METADATA_PATH if path == MCP_PATH else None
        address = request.client.host if request.client else None
        # §6: a redemption is the descriptor's alone, so no Authorization header is read on it.
        # Decided on the path the router matches, so no other route is reached without a caller.
        pull = request.method == "GET" and PULL_PATH.fullmatch(request.scope["path"]) is not None
        if d.throttle.holds(address):
            d.throttle.count(address, refused=True)
            return out(refusal() if pull else unauthorized(metadata))
        token = None if pull else d.caller(request.headers.get("authorization"))
        if token is None and not pull:
            d.throttle.count(address, refused=False)
            return out(unauthorized(metadata))
        if path == MCP_PATH and token.principal == "interactive" and not isinstance(
                token, GrantToken):
            # identity.md §7 (the Chief, on #310): the owner's container Token, interactive and
            # never expiring, is no credential at /mcp, so an MCP client is never handed it.
            d.throttle.count(address, refused=False)
            return out(unauthorized(metadata))
        if path == MCP_PATH and request.method in ("GET", "DELETE"):
            # identity.md §7: a stateless /mcp opens no stream and has no session to end. The
            # transport's 405, the same for every verified caller; the 401 above came first.
            return out(_json(405, {"error": "method_not_allowed"}, {"Allow": "POST"}))
        if malformed([request.scope["path"], *request.query_params.multi_items()]):
            return out(invalid())  # §3: a malformed request, answered before any lookup
        request.state.token = token
        # identity.md §3a: every entry the request appends names an agent's person
        # (`details.for`) or the terminal a person's request came through (`details.terminal`).
        with attributed(token):
            return out(await call_next(request))

    @app.exception_handler(Invalid)
    async def on_invalid(request: Request, exc: Invalid):
        return invalid()

    @app.exception_handler(AmbiguousRef)
    async def on_ambiguous(request: Request, exc: AmbiguousRef):
        # §3: the matches named are only nodes the token covers; the refusal is a read too.
        d.probe(request.state.token, None)
        return ambiguous(exc.paths)

    # -- reads ----------------------------------------------------------------------------------
    def with_pull(token: Token, entry: dict[str, Any]) -> dict[str, Any]:
        """§6: an artifact whose bytes do not ride inline carries Trust's grant and its URL beside
        the item (§4.1), or nothing. Decided on the item as served: one small and `text/*` enough
        to ride inline that does not (an agent's, promoted after its write) is asked about too."""
        item = entry["item"]
        if item["kind"] != "artifact" or "inline" in item["content"]:
            return entry
        grant = c.trust.authorize_pull(token, ContextItem.from_dict(item))
        return {**entry, "grant": grant, "grant_url": grant_url(grant)} if grant else entry

    @app.get("/v1/fetch")
    async def fetch(request: Request):
        token: Token = request.state.token
        params = request.query_params
        _only(params, {"scope", "query", "kind"})
        kinds = None
        if params.get("kind"):
            kinds = params["kind"].split(",")
            if any(k not in KINDS for k in kinds):
                raise Invalid
        query = params.get("query") or None
        ref = params.get("scope") or None
        node = d.scope(token, ref)
        if node is None:
            d.probe(token, ref)
            return refusal()
        result = c.resolver.resolve(node, token=token, actor=token.owner, kinds=kinds, text=query)
        if result["scope"] is None:
            return refusal()  # the resolver appended the probe
        return _json(200, {
            "scope": result["scope"],
            "chain": result["chain"],
            "items": [
                with_pull(token, {k: e[k] for k in ("item", "layer", "layer_type", "shadowed_by")})
                for e in result["items"]
            ],
        })

    @app.get("/v1/find")
    async def find_items(request: Request):
        token: Token = request.state.token
        params = request.query_params
        _only(params, {"q"})
        q = params.get("q", "")
        try:
            query = parse(q)
        except QueryError as e:
            raise Invalid from e
        if not token.has("fetch"):
            d.probe(token, None)
            return refusal()
        hits = find(c, token, query)
        c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                        subject=None, scope=None, client=token.client, query=q,
                        items=[i.id for _, i in hits], layers=[], withheld=0)
        return _json(200, {"items": [d.entry(i.to_dict(), n) for n, i in hits]})

    @app.get("/v1/items/{item_id}")
    async def item(request: Request, item_id: str):
        token: Token = request.state.token
        _only(request.query_params, set())
        found = c.store.get(item_id)
        node = c.backend.get_node(found.scope) if found else None
        if found is None or node is None or not d.readable(token, found, node):
            d.probe(token, item_id)
            return refusal()
        c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                        subject=found.id, scope=node.id, client=token.client,
                        items=[found.id], layers=[node.id], withheld=0)
        return _json(200, with_pull(token, d.entry(found.to_dict(), node)))

    @app.get("/v1/inbox")
    async def inbox(request: Request):
        token: Token = request.state.token
        _only(request.query_params, set())
        box = c.nodes.inbox()
        if box is None or not token.has("fetch") or not c.trust.covers(token, box):
            d.probe(token, "inbox")
            return refusal()
        held = c.store.inbox_items()
        rows = [(n, i) for n, i in held if c.resolver.serve(i, n)]
        c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                        subject=box.id, scope=box.id, client=token.client, layers=["inbox"],
                        items=[i.id for _, i in rows], withheld=len(held) - len(rows))
        return _json(200, {"items": [d.entry(i.to_dict(), n) for n, i in rows]})

    @app.get("/v1/scopes")
    async def scopes(request: Request):
        token: Token = request.state.token
        _only(request.query_params, {"under"})
        ref = request.query_params.get("under") or None
        node = d.scope(token, ref)
        if node is None or not token.has("fetch"):
            d.probe(token, ref)
            return refusal()
        children = [n for n in c.backend.list_nodes(parent=node.id) if c.trust.covers(token, n)]
        out = sorted((d.node(n) for n in children), key=lambda n: n["path"])
        c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                        subject=node.id, scope=node.id, client=token.client, items=[],
                        layers=[], nodes=[n["id"] for n in out], withheld=0)
        return _json(200, {"nodes": out})

    @app.get("/v1/pending")
    async def pending(request: Request):
        token: Token = request.state.token
        _only(request.query_params, set())
        if token.principal != "interactive":
            d.probe(token, "pending")
            return refusal()
        queue = c.trust.pending()
        # §4.4: an artifact still staged past the retention days is asked about under `staged`,
        # instead of under `items`, until a person promotes or tombstones it.
        days = c.config_value("blobs.staging_retention_days")
        cutoff = c.uploads.clock() - days * 86400
        waiting = c.uploads.staged_items()
        items, staged = [], []
        for i in queue["items"]:
            n = c.backend.get_node(i.scope)
            if n is not None and i.status == "unverified" and c.trust.covers(token, n):
                created = calendar.timegm(time.strptime(i.lifecycle["created_at"],
                                                        "%Y-%m-%dT%H:%M:%SZ"))
                old = i.id in waiting and created <= cutoff
                (staged if old else items).append(i.to_dict())
        proposals = [p for p in queue["proposals"] if c.trust.decides_over(token, p)]
        wire = [{("from" if k == "from_" else k): v for k, v in p.items()} for p in proposals]
        orphans = c.uploads.orphans(token, admin=token.has("admin") and "*" in token.scopes)
        uploads = [{"upload": r["id"], **{k: r[k] for k in ORPHAN_KEYS}} for r in orphans]
        c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                        client=token.client, view="pending", items=[i["id"] for i in items],
                        staged=[i["id"] for i in staged], uploads=[u["upload"] for u in uploads],
                        proposals=[p["id"] for p in proposals], layers=[], withheld=0)
        return _json(200, {"items": items, "proposals": wire, "uploads": uploads,
                           "staged": staged})

    # -- writes without a confirm ---------------------------------------------------------------
    @app.post("/v1/items")
    async def add(request: Request):
        token: Token = request.state.token
        _only(request.query_params, set())
        if not token.has("remember"):
            # The capability first: a token that may not write never makes the door read a body.
            d.probe(token, None)
            return refusal()
        body = await _object(request, {"body", "kind", "scope", "key", "tags", "upload"}, set())
        kind = _str(body.get("kind"), optional=True, limit=32) or "memory"
        # Text in its body, or an artifact through an upload (§4.4): one or the other.
        if kind not in KINDS or (kind == "artifact") != ("upload" in body) or (
                ("body" in body) == ("upload" in body)):
            raise Invalid
        text = _str(body["body"], limit=BODY_MAX_BYTES) if "body" in body else None
        upload = _str(body["upload"], limit=64) if "upload" in body else None
        ref = _str(body.get("scope"), optional=True)
        key = _str(body.get("key"), optional=True, limit=255)
        tags = body.get("tags") or []
        if not isinstance(tags, list) or not all(isinstance(t, str) and t for t in tags):
            raise Invalid
        node = None
        if ref is not None:
            node = d.scope(token, ref)
            if node is None:
                d.probe(token, ref)
                return refusal()
        try:
            if upload is not None:
                written = c.uploads.item(token, upload, scope=node, key=key, tags=tags)
            else:
                written = c.store.add(body=text, kind=kind, scope=node, key=key, tags=tags,
                                      token=token, actor=token.owner, principal=token.principal)
        except StoreError:
            written = None
        if written is None:
            d.probe(token, upload or ref)
            return refusal()
        return _json(200, {"item": written.to_dict()})

    # -- artifact upload (§4.4) -----------------------------------------------------------------
    @app.post("/v1/uploads")
    async def open_upload(request: Request):
        token: Token = request.state.token
        _only(request.query_params, set())
        if not token.has("remember"):
            d.probe(token, None)
            return refusal()
        fields = {"scope", "name", "mime", "size", "sha256"}
        body = await _object(request, fields, fields)
        ref = _str(body["scope"])
        if not valid_open(body["name"], body["mime"], body["size"], body["sha256"],
                          limit=c.config_value("blobs.upload_max_bytes")):
            raise Invalid
        node = d.scope(token, ref)
        if node is None:
            d.probe(token, ref)
            return refusal()
        try:
            record = c.uploads.open(token, scope=node, name=body["name"], mime=body["mime"],
                                    size=body["size"], sha256=body["sha256"])
        except TooManyUploads:
            return _json(429, {"error": "too_many_uploads"})
        return _json(200, {"upload": record["id"], "expires_at": record["expires_at"]})

    @app.put("/v1/uploads/{upload_id}")
    async def upload_bytes(request: Request, upload_id: str):
        token: Token = request.state.token
        _only(request.query_params, set())
        record = c.uploads.live(token, upload_id)
        if record is None:
            # Unknown, expired, discarded and another principal's alike; no byte is read.
            d.probe(token, upload_id)
            return refusal()
        outcome = c.uploads.put(token, upload_id, await _exactly(request, record["size"]))
        if outcome is None:
            d.probe(token, upload_id)
            return refusal()
        if outcome != "staged":
            return invalid()
        return _json(200, {"upload": upload_id, "sha256": record["sha256"]})

    @app.delete("/v1/uploads/{upload_id}")
    async def discard_upload(request: Request, upload_id: str):
        token: Token = request.state.token
        _only(request.query_params, set())
        admin = token.principal == "interactive" and token.has("admin") and "*" in token.scopes
        if not c.uploads.discard(token, upload_id, admin=admin):
            d.probe(token, upload_id)
            return refusal()
        return _json(200, {"result": "discarded"})

    @app.post("/v1/scopes")
    async def make(request: Request):
        token: Token = request.state.token
        _only(request.query_params, set())
        body = await _object(request, {"type", "name", "parent"}, {"type", "name"})
        kind = _str(body["type"], limit=32)
        name = body["name"]
        if kind not in _CREATABLE or not valid_name(name):  # §4.5's rule, before any lookup
            raise Invalid
        ref = _str(body.get("parent"), optional=True)
        parent = d.scope(token, ref) if ref is not None else c.nodes.user_root()
        if parent is None or not c.trust.covers(token, parent):
            d.probe(token, ref)
            return refusal()
        try:
            node = c.nodes.create(kind, name, parent, token=token, actor=token.owner,
                                  principal=token.principal)
        except StructureError:
            d.probe(token, ref)
            return refusal()
        made = d.node(node)
        if not token.has("fetch"):
            made["path"] = None  # §4.1 item 8: a computed path names ancestors; only `fetch` reads
        return _json(200, {"node": made})

    # -- the confirm (§4.2) ---------------------------------------------------------------------
    def names(delta: list[dict[str, Any]]) -> list[str]:
        """Who would newly see it: each grant's or registration's display name, a token's client."""
        granted = {t.id: t for t in c.identity.audience_tokens()}
        return [granted[m["token"]].name if m["token"] in granted else m["client"] for m in delta]

    def origin_of(request: Request) -> str | None:
        """The request's browser origin, when it is one this container answers (identity.md §6):
        the relying party a WebAuthn credential belongs to. Any other origin is no origin."""
        origin = request.headers.get("origin")
        return origin if origin in d.origins() else None

    def first_leg(token: Token, *, act: str, subject: str, destination: str | None,
                  delta: list[dict[str, Any]], origin: str | None, **extra: Any) -> Response:
        newly = names(delta)
        # Showing who would newly see an item is a read of credential metadata (§4.2 item 2).
        c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                        client=token.client, subject=subject, items=[], layers=[], withheld=0,
                        confirm_for=act, newly=newly, **extra)
        return _json(200, {**c.confirm.issue(token, act=act, subject=subject,
                                             destination=destination,
                                             delta=[m["token"] for m in delta], newly=newly,
                                             origin=origin), **extra})

    def presented(body: dict[str, Any]) -> dict[str, Any] | None:
        value = body.get("confirm")
        if value is None:
            return None
        if (not isinstance(value, dict) or set(value) - {"challenge", "proof", "assertion"}
                or value.get("proof") not in ("biometric", "button")):
            raise Invalid
        _str(value.get("challenge"), limit=128)  # a challenge id, never empty (§3: a 400)
        return value

    class Refused(Exception):
        """The act the confirm was for cannot land: everything rolls back, the answer is §3's."""

    async def move_or_copy(request: Request, item_id: str, act: str) -> Response:
        token: Token = request.state.token
        origin = origin_of(request)
        _only(request.query_params, set())
        body = await _object(request, {"to", "confirm"}, {"to"})
        ref = _str(body["to"])
        proof = presented(body)
        item = c.store.get(item_id)
        to = d.scope(token, ref)
        if item is None or to is None:
            d.probe(token, item_id)
            return refusal()
        try:
            _frm, delta = c.trust.gate(item, to, token=token, act=act)
        except TrustError:
            d.probe(token, item_id)
            return refusal()
        if not delta or token.principal != "interactive":
            # Nobody new would see it: the silent pass. Or a client principal, whose widening act
            # parks for a person to decide, and whose `confirm` is ignored (§4.2 item 6).
            r = (c.trust.move if act == "move" else c.trust.copy)(
                item, to, token=token, actor=token.owner)
            if r.get("gate") == "pending":
                return _json(200, {"result": "pending", "proposal": r["proposal"]["id"]})
            landed = c.store.get(item.id) if act == "move" else r["item"]
            return _json(200, {"result": "moved" if act == "move" else "copied",
                               "item": landed.to_dict()})
        if proof is None:
            return first_leg(
                token, act=act, subject=item.id, destination=to.id, delta=delta, origin=origin
            )
        try:
            with c.backend.atomic():
                # Recomputed under the lock: the confirm binds the delta as it stands now.
                _frm, delta = c.trust.gate(item, to, token=token, act=act)
                landed = None
                if not delta:
                    # Nobody new would see it any more: the silent pass that is now due, with
                    # nothing to confirm (a1r on #289).
                    r = (c.trust.move if act == "move" else c.trust.copy)(
                        item, to, token=token, actor=token.owner)
                    landed = c.store.get(item.id) if act == "move" else r["item"]
                else:
                    reason = c.confirm.conclude(token, proof, act=act, subject=item.id,
                                                destination=to.id,
                                                delta=[m["token"] for m in delta], origin=origin)
                    if reason is None:
                        landed = c.trust.confirmed(item, to, token=token, actor=token.owner,
                                                   act=act, delta=delta,
                                                   step_up=c.confirm.last_step_up_seq())
        except (TrustError, HumanOnly):
            d.probe(token, item_id)
            return refusal()
        if landed is None:
            return first_leg(
                token, act=act, subject=item.id, destination=to.id, delta=delta, origin=origin
            )
        return _json(200, {"result": "moved" if act == "move" else "copied",
                           "item": landed.to_dict()})

    @app.post("/v1/items/{item_id}/move")
    async def move(request: Request, item_id: str):
        return await move_or_copy(request, item_id, "move")

    @app.post("/v1/items/{item_id}/copy")
    async def copy(request: Request, item_id: str):
        return await move_or_copy(request, item_id, "copy")

    async def optional_body(request: Request) -> dict[str, Any]:
        if not await request.body():
            return {}
        return await _object(request, {"confirm"}, set())

    async def decide(request: Request, proposal_id: str, act: str) -> Response:
        token: Token = request.state.token
        origin = origin_of(request)
        _only(request.query_params, set())
        proof = presented(await optional_body(request))
        p = c.backend.get_proposal(proposal_id)
        if (token.principal != "interactive" or p is None or p["status"] != "open"
                or not c.trust.decides_over(token, p)):
            d.probe(token, proposal_id)
            return refusal()
        # Approving a parked widening act shows who would newly see it, and the confirm binds that
        # delta; a denial changes nobody's view (§4.2 item 1; a1r on #289).
        widens = list(p.get("audience_delta") or []) if act == "approve" else []
        if proof is None:
            return first_leg(
                token, act=act, subject=proposal_id, destination=None, delta=widens, origin=origin
            )
        outcome: str | None = None
        result: dict[str, Any] = {}
        try:
            with c.backend.atomic():
                reason = c.confirm.conclude(token, proof, act=act, subject=proposal_id,
                                            destination=None,
                                            delta=[m["token"] for m in widens], origin=origin)
                if reason is None:
                    try:
                        if act == "approve":
                            result = c.trust.execute(proposal_id, token=token, actor=token.owner)
                            outcome = "executed"
                        else:
                            c.trust.deny(proposal_id, token=token, actor=token.owner)
                            outcome = "denied"
                    except TrustError as e:
                        current = c.backend.get_proposal(proposal_id)
                        if current is None or current["status"] != "stale":
                            raise Refused from e
                        outcome = "stale"  # kept: the stale status and its event commit
        except (Refused, HumanOnly):
            d.probe(token, proposal_id)
            return refusal()
        if outcome is None:
            return first_leg(
                token, act=act, subject=proposal_id, destination=None, delta=widens, origin=origin
            )
        if outcome == "executed":
            # A move's item is where it went; a copy's is the new one, not its source.
            made = result.get("copies") or p["items"]
            landed = c.store.get(made[0])
            return _json(200, {"result": "executed", "item": landed.to_dict() if landed else None})
        return _json(200, {"result": outcome})

    @app.post("/v1/pending/{proposal_id}/approve")
    async def approve(request: Request, proposal_id: str):
        return await decide(request, proposal_id, "approve")

    @app.post("/v1/pending/{proposal_id}/deny")
    async def deny(request: Request, proposal_id: str):
        return await decide(request, proposal_id, "deny")

    # -- tombstone (§4): a person's, at once, or with the confirm where a person promoted it -----
    def tombstone_leg(token: Token, item: Any, origin: str | None) -> Response:
        """A promoted item's first leg: nobody newly sees anything, and it names what it removes,
        a read audited as every first leg is (§4.2 item 2)."""
        named = {"item": item.id, "kind": item.kind, "auto_title": item.content.get("auto_title")}
        return first_leg(token, act="tombstone", subject=item.id, destination=None, delta=[],
                         origin=origin, tombstones=named)

    @app.delete("/v1/items/{item_id}")
    async def tombstone(request: Request, item_id: str):
        token: Token = request.state.token
        origin = origin_of(request)
        _only(request.query_params, set())
        if token.principal != "interactive" or not token.has("organize"):
            d.probe(token, item_id)  # one who may not act here never makes the door read a body
            return refusal()
        proof = presented(await optional_body(request))
        leg, gone = None, None
        with c.backend.atomic():
            item = c.store.get(item_id)  # as it stands under the lock (a6 on #289)
            # A verified item, or one a person promoted whatever its status now, takes the
            # confirm. A refused proof's `step_up` commits; a fresh first leg follows (§4.2 item 4).
            if (item is not None and c.uploads.tombstonable(token, item)
                    and c.uploads.promoted(item)
                    and (proof is None or c.confirm.conclude(
                        token, proof, act="tombstone", subject=item.id, destination=None,
                        delta=[], origin=origin) is not None)):
                leg = item
            else:  # never promoted, a `confirm` with it ignored; or confirmed
                gone = c.uploads.tombstone(token, item_id)
        if leg is not None:
            return tombstone_leg(token, leg, origin)
        if gone is None:
            d.probe(token, item_id)
            return refusal()
        return _json(200, {"result": "tombstoned"})

    @app.post("/v1/items/{item_id}/promote")
    async def promote(request: Request, item_id: str):
        token: Token = request.state.token
        origin = origin_of(request)
        _only(request.query_params, set())
        proof = presented(await optional_body(request))
        item = c.store.get(item_id)
        node = c.backend.get_node(item.scope) if item else None
        if (token.principal != "interactive" or item is None or node is None
                or item.status != "unverified" or not c.trust.covers(token, node)):
            d.probe(token, item_id)
            return refusal()
        if proof is None:
            return first_leg(
                token, act="promote", subject=item.id, destination=None, delta=[], origin=origin
            )
        promoted = None
        try:
            with c.backend.atomic():
                reason = c.confirm.conclude(token, proof, act="promote", subject=item.id,
                                            destination=None, delta=[], origin=origin)
                if reason is None:
                    promoted = c.trust.promote(item, token=token, actor=token.owner)
        except (TrustError, HumanOnly):
            d.probe(token, item_id)
            return refusal()
        if promoted is None:
            return first_leg(
                token, act="promote", subject=item.id, destination=None, delta=[], origin=origin
            )
        return _json(200, {"result": "promoted", "item": promoted.to_dict()})

    # -- what this door serves (§4.6) -----------------------------------------------------------
    @app.get("/v1/limits")
    async def limits(request: Request):
        """To any valid token, a `client` principal's included: facts about the caller's own
        container and no secret. Two config keys and one constant, and nothing else: it sets
        nothing and serves no other key."""
        token: Token = request.state.token
        _only(request.query_params, set())
        c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                        client=token.client, read="limits", items=[], layers=[], withheld=0)
        return _json(200, {
            "contract": CONTRACT_VERSION,
            "features": list(FEATURES),
            "upload_max_bytes": c.config_value("blobs.upload_max_bytes"),
            "inline_max_bytes": c.config_value("blobs.inline_max_bytes"),
            "uploads_held_max": MAX_HELD,
        })

    # -- grants (§4.3) --------------------------------------------------------------------------
    def at_terminal(token: Token) -> bool:
        """A person's token issued to a terminal's own client (identity.md §3a). It is its person,
        but it gives no one access: the routes that give access, or keep or remove a confirm
        credential, are §3's refusal to it before any leg and before its body is read (§4.3)."""
        return terminal_of(token) is not None

    def grantor(token: Token | None) -> bool:
        """A person signed in at the provider, with `admin` over the whole container. A container
        `Token` names no `sub`; an agent is never served who else holds access."""
        return (isinstance(token, GrantToken) and token.principal == "interactive"
                and token.has("admin") and "*" in token.scopes)

    def granted(g: dict[str, Any]) -> dict[str, Any]:
        """§4.3's `<grant>`."""
        return {k: g[k] for k in ("sub", "name", "capabilities", "scopes", "created_at")}

    scopes_max = 64  # the most scope refs a grant names: each is a lookup, made before any leg

    def ask(token: Token, *, subject: str, destination: str, opens: list[tuple[str, str]],
            origin: str | None) -> Response:
        """§4.2's first leg for a grant: as `first_leg`, but naming whom it opens to as
        `Identity.opens` does, since a person not yet granted is in no audience to name."""
        newly = [name for _, name in opens]
        c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                        client=token.client, subject=subject, items=[], layers=[], withheld=0,
                        confirm_for="grant.add", newly=newly)
        return _json(200, c.confirm.issue(token, act="grant.add", subject=subject,
                                          destination=destination,
                                          delta=[member for member, _ in opens], newly=newly,
                                          origin=origin))

    @app.get("/v1/grants")
    async def list_grants(request: Request):
        token: Token = request.state.token
        _only(request.query_params, set())
        if not grantor(token):
            d.probe(token, "grants")
            return refusal()
        live = [granted(g) for g in c.backend.list_user_grants() if not g["revoked"]]
        c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                        client=token.client, read="grants", items=[], layers=[], withheld=0,
                        grants=[g["sub"] for g in live])
        return _json(200, {"grants": live})

    @app.post("/v1/grants")
    async def add_grant(request: Request):
        token: Token = request.state.token
        origin = origin_of(request)
        _only(request.query_params, set())
        if not grantor(token) or at_terminal(token):  # the door never reads this caller's body
            d.probe(token, "grants")
            return refusal()
        body = await _object(request, {"sub", "name", "role", "capabilities", "scopes", "confirm"},
                             {"sub", "name", "scopes"})
        proof = presented(body)
        refs = body["scopes"]
        try:  # as `grant_user` checks them, so it never refuses one under the lock
            sub = c.identity.user_id(body["sub"])
            name = display_name(body["name"])
            caps = c.identity.expand(body.get("role"), body.get("capabilities"))
        except ValueError as e:
            raise Invalid from e
        if not isinstance(refs, list) or not 0 < len(refs) <= scopes_max:
            raise Invalid
        refs = [_str(r) for r in refs]
        # The lookups, after every shape check (§3): a ref resolves as §3's do (an ambiguous tail
        # is its 409), and the grant holds the node ids, never the refs.
        nodes = [d.scope(token, r) for r in refs if r != "*"]
        scopes = ["*"] if "*" in refs else sorted({n.id for n in nodes if n is not None})
        # No grant exceeds the caller's own: wider capabilities or scopes are §3's refusal.
        if None in nodes or c.identity.exceeds(token, caps, scopes):
            d.probe(token, sub)
            return refusal()
        kw = {"actor": token.owner, "principal": token.principal}
        if c.identity.refuse_narrowing(sub, caps, scopes, **kw):  # before any leg (§4.3)
            return _json(409, {"error": "last_admin"})
        # The challenge binds the grant as it would land, beside its `sub` (the subject).
        terms = json.dumps({"name": name, "capabilities": caps, "scopes": scopes}, sort_keys=True)
        if proof is None:
            return ask(token, subject=sub, destination=terms,
                       opens=c.identity.opens(sub, name, caps, scopes), origin=origin)
        made, reason, opens = None, None, []
        with c.backend.atomic():
            # As on DELETE: the caller as their grant stands now, so a revoke or a narrowing since
            # the door counts; the door's token concludes, as only it carries the sign-in time.
            now = c.identity.refresh(token)
            if grantor(now) and not c.identity.exceeds(now, caps, scopes):
                opens = c.identity.opens(sub, name, caps, scopes)  # the delta as it stands now
                reason = c.confirm.conclude(token, proof, act="grant.add", subject=sub,
                                            destination=terms, delta=[m for m, _ in opens],
                                            origin=origin, fresh_sign_in=True)
                if reason is None:
                    try:
                        made = c.identity.grant_user(sub, name=name, capabilities=caps,
                                                     scopes=scopes, **kw)
                    except LastAdmin:
                        return _json(409, {"error": "last_admin"})  # its refusal commits
        if reason is not None:
            return ask(token, subject=sub, destination=terms, opens=opens, origin=origin)
        if made is None:  # the caller's own grant changed since the door
            d.probe(token, sub)
            return refusal()
        return _json(200, {"grant": granted(made)})

    @app.delete("/v1/grants/{sub}")
    async def revoke_grant(request: Request, sub: str):
        token: Token = request.state.token
        origin = origin_of(request)
        _only(request.query_params, set())
        if not grantor(token):  # a caller who may not act here never makes the door read a body
            d.probe(token, sub)
            return refusal()
        proof = presented(await optional_body(request))
        grant = c.backend.get_user_grant(sub)
        if grant is None or grant["revoked"]:
            d.probe(token, sub)
            return refusal()

        def first() -> Response:  # whose access it ends, and every registration it takes with it
            ends: dict[str, Any] = {"grant": {"sub": sub, "name": grant["name"]}}
            for kind, key in (("agent", "agents"), ("terminal", "terminals")):
                named = [{"client_id": r["client_id"], "name": r["name"]}
                         for r in c.identity.serving(sub, kind)]
                if named or kind == "agent":  # `terminals` only where it ends one
                    ends[key] = named
            return first_leg(token, act="grant.revoke", subject=sub, destination=None, delta=[],
                             origin=origin, revokes=ends)

        # Narrowing your own access is never gated; ending someone else's is. `last_admin` is
        # `revoke_user`'s, under the lock: your own revoke has no leg to come before, and another
        # person's grant is never the last while the caller, re-read there, holds one.
        gated = f"user:{sub}" != person_of(token)
        if gated and proof is None:
            return first()
        revoked, reason = False, None
        with c.backend.atomic():
            # The caller as their grant stands now, as approve re-reads its decider (#118): a
            # revoke or a narrowing since the door verified them counts. The token the door
            # verified is the one that concludes, since only it carries the sign-in time.
            if grantor(c.identity.refresh(token)):
                if gated:
                    reason = c.confirm.conclude(token, proof, act="grant.revoke", subject=sub,
                                                destination=None, delta=[], origin=origin,
                                                fresh_sign_in=True)
                if reason is None:
                    try:
                        revoked = c.identity.revoke_user(sub, actor=token.owner,
                                                         principal=token.principal)
                    except LastAdmin:
                        return _json(409, {"error": "last_admin"})  # its refusal commits
        if reason is not None:
            return first()
        if not revoked:  # the caller's grant or the target's changed since the door
            d.probe(token, sub)
            return refusal()
        return _json(200, {"result": "revoked"})

    # -- agents (§4.3) --------------------------------------------------------------------------
    def registrant(token: Token | None) -> bool:
        """A person signed in at the provider, on any live grant: whose agents these are. A
        container `Token` names no `sub`; an agent is never served who else holds access."""
        return isinstance(token, GrantToken) and token.principal == "interactive"

    def places(token: Token | None, scopes: list[str]) -> bool:
        """Whether each scope is `"*"` or the id of a node that exists and `token` covers, found
        by its id alone (§4.3). `exceeds` alone would pass an absent id for a caller holding `*`."""
        return token is not None and all(
            s == "*" or ((n := c.backend.get_node(s)) is not None and c.trust.covers(token, n))
            for s in scopes)

    def agent(r: dict[str, Any], seen: dict[tuple[str, str], str]) -> dict[str, Any]:
        """§4.3's `<agent>`, `last_seen` read from the chain: null for an agent never seen."""
        keys = ("client_id", "name", "sub", "capabilities", "scopes", "created_at")
        return {**{k: r[k] for k in keys}, "last_seen": seen.get((r["client_id"], r["sub"]))}

    def own_client(token: Token | None) -> bool:
        """A person's provider token issued to this container's own client (§4.3's `GET
        /v1/grant`): never an agent, a container `Token` or a registered terminal's token."""
        return (registrant(token) and not at_terminal(token)
                and token.client_id == c.config_value("identity.client_id"))

    @app.get("/v1/grant")
    async def own_grant(request: Request):
        """§4.3: the caller's own live grant, its capabilities by name and each scope a node id
        that exists, or `"*"`; nothing else of it, and nothing of any other grant."""
        token: Token = request.state.token
        _only(request.query_params, set())  # to every caller alike, before their kind is read
        grant = c.backend.get_user_grant(token.sub) if own_client(token) else None
        if grant is None or grant["revoked"]:  # revoked since the door verified the caller too
            d.probe(token, "grant")
            return refusal()
        scopes = [s for s in grant["scopes"] if s == "*" or c.backend.get_node(s) is not None]
        c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                        client=token.client, read="grant", items=[], layers=[], withheld=0)
        return _json(200, {"grant": {"capabilities": sorted(grant["capabilities"]),
                                     "scopes": scopes}})

    @app.get("/v1/agents")
    async def list_agents(request: Request):
        token: Token = request.state.token
        _only(request.query_params, set())
        if not registrant(token):
            d.probe(token, "agents")
            return refusal()
        # The registrations serving this person; for an admin over everything, everyone's.
        live = ([r for r in c.identity.registrations("agent") if not r["revoked"]]
                if grantor(token) else c.identity.serving(token.sub, "agent"))
        seen = c.identity.last_seen(live)
        c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                        client=token.client, read="agents", items=[], layers=[], withheld=0,
                        agents=[{"client_id": r["client_id"], "sub": r["sub"]} for r in live])
        return _json(200, {"agents": [agent(r, seen) for r in live]})

    @app.post("/v1/agents")
    async def add_agent(request: Request):
        token: Token = request.state.token
        origin = origin_of(request)
        _only(request.query_params, set())
        if not registrant(token) or at_terminal(token):  # the door never reads this body
            d.probe(token, "agents")
            return refusal()
        body = await _object(
            request, {"authorization_id", "client_id", "name", "role", "capabilities", "scopes",
                      "confirm"}, {"authorization_id", "client_id", "name", "scopes"})
        proof = presented(body)
        refs = body["scopes"]
        try:  # what the consent page relays; the name is the agent's own claim
            authorization = provider_id(body["authorization_id"])
            client_id = provider_id(body["client_id"])
            name = display_name(body["name"])
            caps = c.identity.expand(body.get("role"), body.get("capabilities"))
        except ValueError as e:
            raise Invalid from e
        if not isinstance(refs, list) or not 0 < len(refs) <= scopes_max:
            raise Invalid
        refs = [_str(r) for r in refs]
        # §4.3, "The whole container is one choice of its own": `"*"` stands alone, and every
        # other entry has the form of a node id and is read as an id alone, so no name is ever
        # read as a place here. Both are shape checks, before any lookup.
        if ("*" in refs and len(refs) != 1) or not all(r == "*" or is_ulid(r) for r in refs):
            raise Invalid
        scopes = ["*"] if refs == ["*"] else sorted(set(refs))
        # This container's own client names a person, never an agent; a registration never
        # exceeds the caller's own grant, and needs no `publish`; an authorization registers once.
        head = c.ledger.tail(1)[-1]["seq"]  # the door reads the chain to here; the lock, past it
        if (client_id == c.config_value("identity.client_id") or not places(token, scopes)
                or c.identity.exceeds(token, caps, scopes) or c.identity.claimed(authorization)):
            d.probe(token, client_id)
            return refusal()
        if c.identity.full(token.sub, client_id):  # a fact about the caller's own, before any leg
            return _json(429, {"error": "too_many_agents"})
        terms = {"capabilities": caps, "scopes": scopes}

        def replaced() -> dict[str, Any] | None:
            """§4.3, "Choosing again": the live registration of this client serving the caller,
            as `GET /v1/agents` serves it to them, which the new one replaces whole."""
            was = c.identity.registration(client_id, token.sub, "agent")
            if was is None or was["revoked"]:
                return None
            return {k: was[k] for k in ("capabilities", "scopes", "created_at")}

        def bound(was: dict[str, Any] | None) -> str:
            # The challenge binds the registration as it would land, beside its client (the
            # subject), and what it replaces, or that it replaces none: what the person is shown
            # is what lands.
            return json.dumps({"authorization_id": authorization, "name": name, **terms,
                               "replaces": was}, sort_keys=True)

        def first() -> Response:  # nobody newly sees anything: the agent is named apart, as itself
            was = replaced()  # as it stands now, for every first leg, a fresh one included
            return first_leg(token, act="agent.add", subject=client_id, destination=bound(was),
                             delta=[], origin=origin,
                             registers={"client_id": client_id, "name": name}, terms=terms,
                             **({"replaces": was} if was is not None else {}))

        if proof is None:
            return first()
        made, reason = None, None
        with c.backend.atomic():
            # As on the grant routes: the caller as their grant stands now, still covering the
            # registration, and each place found again by its id, so a revoke or a place gone
            # since the door registers nothing; the door's token concludes, as only it carries the
            # sign-in time. A client id a terminal's registration names is never an agent's: a
            # proof that would confirm concludes refused, `registered`, and the answer is a fresh
            # first leg, as for every refused proof, so no leg says the id was taken (§4.3).
            now = c.identity.refresh(token)
            if (registrant(now) and places(now, scopes)
                    and not c.identity.exceeds(now, caps, scopes)):
                was = replaced()  # read under the lock: one changed since the first leg mismatches
                taken = c.identity.taken(client_id, "agent")
                reason = c.confirm.conclude(token, proof, act="agent.add", subject=client_id,
                                            destination=bound(was), delta=[], origin=origin,
                                            fresh_sign_in=True,
                                            refusal="registered" if taken else None)
                if reason is None:
                    try:
                        made = c.identity.register_agent(
                            token, client_id, authorization_id=authorization, name=name,
                            capabilities=caps, scopes=scopes, after=head, replaces=was)
                    except TooManyAgents:  # a 16th landed since the door; its step_up commits
                        return _json(429, {"error": "too_many_agents"})
        if reason is not None:
            return first()
        if made is None:  # the caller's grant changed since the door, or the authorization is spent
            d.probe(token, client_id)
            return refusal()
        return _json(200, {"agent": agent(made, c.identity.last_seen([made]))})

    def served(token: Token, sub: str | None) -> str | None:
        """The person whose registration a route names (`sub`, §4.3): the caller, or another
        person only for an admin over the whole container. None is §3's refusal, as it is for a
        client principal and a container `Token`."""
        if not registrant(token):
            return None
        if sub is None or sub == token.sub:
            return token.sub
        return sub if grantor(token) else None

    @app.delete("/v1/agents/{client_id}")
    async def end_agent(request: Request, client_id: str):
        token: Token = request.state.token
        origin = origin_of(request)
        _only(request.query_params, {"sub"})
        sub = served(token, request.query_params.get("sub"))
        # As on the grant routes, a caller who may not act here never makes the door read a body.
        if sub is None:
            d.probe(token, client_id)
            return refusal()
        proof = presented(await optional_body(request))
        found = c.identity.registration(client_id, sub, "agent")  # a terminal's is not one
        if found is None or found["revoked"]:
            d.probe(token, client_id)
            return refusal()
        # Ending your own agent narrows only your own access, so it is never gated, and a confirm
        # sent with it concludes nothing; ending one that serves someone else is gated as
        # registering it was, the challenge bound to the pair (GHSA-c3gg-hwx9-473g).
        gated = sub != token.sub
        binding = {"act": "agent.revoke", "subject": client_id, "destination": sub, "delta": [],
                   "origin": origin}

        def first() -> Response:  # the registration it ends; the name is the agent's own claim
            return first_leg(token, **binding, revokes={"agent": {
                "client_id": client_id, "name": found["name"], "sub": sub}})

        if gated and proof is None:
            return first()
        revoked, reason = False, None
        with c.backend.atomic():
            # Gated, as on the grant routes: the caller as their grant stands now, still an admin
            # over everything; the door's token concludes, as only it carries the sign-in time.
            # Your own: a revoke of your grant since the door ended this registration with it.
            if not gated or grantor(c.identity.refresh(token)):
                if gated:
                    reason = c.confirm.conclude(token, proof, **binding, fresh_sign_in=True)
                if reason is None:
                    revoked = c.identity.revoke_agent(client_id, sub, actor=token.owner,
                                                      principal=token.principal)
        if reason is not None:
            return first()
        if not revoked:  # the caller's grant or the registration changed since the door
            d.probe(token, client_id)
            return refusal()
        return _json(200, {"result": "revoked"})

    def log_limit(params: Any) -> int:
        """§4.3: a log's `limit`, 1 to 200 and 50 when absent; any other value is §3's `400`."""
        raw = params.get("limit", "50")
        limit = int(raw) if re.fullmatch(r"[0-9]{1,3}", raw) else 0
        if not 0 < limit <= 200:
            raise Invalid
        return limit

    def log_of(token: Token, entries: list[dict[str, Any]], limit: int,
               own: Any = None) -> tuple[list[dict[str, Any]], list[int], int]:
        """§4.3's log reader, newest first, over `entries`: the lines served, their chain
        positions and how many were passed over to serve them. It omits, with no marker and no
        count, a refused act, a probe (§4's names no subject), and a line whose subject, or scope
        where it names one, the reader does not cover today; `own` names the further subjects a
        terminal's log serves."""
        sight: dict[str, bool] = {}

        def sees(ref: str | None) -> bool:
            # Covered today: an item by the node it sits in now, a node by itself, and anything
            # else (a proposal, an upload, a client id) never, but what `own` serves. A
            # tombstoned or quarantined item reads as absent, as at every item route (§3).
            if ref is None:
                return False
            if ref not in sight:
                item = c.store.get(ref)  # None for a tombstoned item
                node = c.backend.get_node(item.scope if item else ref)
                sight[ref] = (node is not None and c.trust.covers(token, node)
                              and (item is None or item.status != "quarantined"))
            return sight[ref]

        lines: list[dict[str, Any]] = []
        positions: list[int] = []  # their chain positions, on the record only: served, a position
        withheld = 0               # would count what the reader cannot see (§4.3, "no count")
        for e in reversed(entries):
            if len(lines) == limit:
                break
            subject = e["subject"]
            if (e["details"].get("outcome") != "refused"
                    and (sees(subject) or (own is not None and own(subject)))
                    and (e["scope"] is None or sees(e["scope"]))):
                lines.append({k: e[k] for k in ("ts", "event", "subject", "scope")})
                positions.append(e["seq"])
            else:
                withheld += 1
        return lines, positions, withheld

    @app.get("/v1/agents/{client_id}/log")
    async def agent_log(request: Request, client_id: str):
        token: Token = request.state.token
        params = request.query_params
        _only(params, {"sub", "limit"})
        limit = log_limit(params)
        sub = served(token, params.get("sub"))
        # A revoked registration's log is still its history, there to review after ending it. A
        # terminal's client id names no agent here (§4.3).
        if sub is None or c.identity.registration(client_id, sub, "agent") is None:
            d.probe(token, client_id)
            return refusal()
        lines, positions, withheld = log_of(token, c.identity.acted(client_id, sub), limit)
        # `withheld`, on the record only: the lines passed over to serve these.
        c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                        client=token.client, subject=client_id, read="agent_log", items=[],
                        layers=[], withheld=withheld, agent={"client_id": client_id, "sub": sub},
                        entries=positions)
        return _json(200, {"entries": lines})

    # -- terminals (§4.3) -----------------------------------------------------------------------
    def terminal(r: dict[str, Any], seen: dict[tuple[str, str], str],
                 ended: dict[tuple[str, str], str] | None = None) -> dict[str, Any]:
        """§4.3's `<terminal>`, `last_seen` read from the chain, null for one not used yet; one
        that gave a `machine` carries it, and an ended one also carries `ended_at`, read from its
        `identity.revoke`."""
        pair = (r["client_id"], r["sub"])
        out = {**{k: r[k] for k in ("client_id", "name", "sub", "created_at")},
               "last_seen": seen.get(pair)}
        if "machine" in r:
            out["machine"] = r["machine"]
        if ended is not None:
            out["ended_at"] = ended.get(pair)
        return out

    @app.get("/v1/terminals")
    async def list_terminals(request: Request):
        token: Token = request.state.token
        params = request.query_params
        _only(params, {"ended"})
        if params.get("ended", "1") != "1":  # absent, or exactly `1`: anything else is a 400
            raise Invalid
        ended = "ended" in params
        if not registrant(token):
            d.probe(token, "terminals")
            return refusal()
        # The live terminals signed in as this person, or with `ended=1` the ended ones; for an
        # admin over everything, everyone's. Never an agent (§4.3).
        mine = c.identity.registrations("terminal", sub=None if grantor(token) else token.sub)
        listed = [r for r in mine if bool(r["revoked"]) == ended]
        seen = c.identity.terminal_last_seen(listed)
        c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                        client=token.client, read="terminals", items=[], layers=[], withheld=0,
                        terminals=[{"client_id": r["client_id"], "sub": r["sub"]} for r in listed])
        gone = c.identity.terminal_ended(listed) if ended else None
        return _json(200, {"terminals": [terminal(r, seen, gone) for r in listed]})

    @app.post("/v1/terminals")
    async def add_terminal(request: Request):
        token: Token = request.state.token
        origin = origin_of(request)
        _only(request.query_params, set())
        # A person's own, from a browser: a terminal's token registers nothing, and the door never
        # reads its body, nor that of a caller who may not act here.
        if not registrant(token) or at_terminal(token):
            d.probe(token, "terminals")
            return refusal()
        body = await _object(request,
                             {"authorization_id", "client_id", "name", "machine", "confirm"},
                             {"authorization_id", "client_id", "name"})
        proof = presented(body)
        try:  # what the hand-off's page relays; the name and the machine are the terminal's own
            authorization = provider_id(body["authorization_id"])
            client_id = provider_id(body["client_id"])
            name = display_name(body["name"])
            machine = display_name(body["machine"]) if "machine" in body else None
        except ValueError as e:
            raise Invalid from e
        # This container's own client names a person, and that id is no secret; an authorization
        # registers once. Whether this client id was registered here is said by no leg (below).
        head = c.ledger.tail(1)[-1]["seq"]  # the door reads the chain to here; the lock, past it
        if client_id == c.config_value("identity.client_id") or c.identity.claimed(authorization):
            d.probe(token, client_id)
            return refusal()
        if c.identity.terminals_full(token.sub):  # the caller's own fact, before any leg
            return _json(429, {"error": "too_many_terminals"})
        # The challenge binds the registration as it would land, beside its client (the subject).
        bound = {"authorization_id": authorization, "name": name}
        shown = {"client_id": client_id, "name": name}
        if machine is not None:
            bound["machine"] = shown["machine"] = machine
        terms = json.dumps(bound, sort_keys=True)

        def first() -> Response:  # nobody newly sees anything: the terminal is named apart
            return first_leg(token, act="terminal.add", subject=client_id, destination=terms,
                             delta=[], origin=origin, signs_in=shown)

        if proof is None:
            return first()
        made, reason = None, None
        with c.backend.atomic():
            # As on POST /v1/agents: the caller as their grant stands now. A client id any
            # registration here names, of either kind, live or ended, for anyone, is never a
            # terminal's: a proof that would confirm concludes refused, `registered`, answered with
            # a fresh first leg as every refused proof is, so a terminal ended never returns.
            now = c.identity.refresh(token)
            if registrant(now):
                taken = c.identity.taken(client_id, "terminal")
                reason = c.confirm.conclude(token, proof, act="terminal.add", subject=client_id,
                                            destination=terms, delta=[], origin=origin,
                                            fresh_sign_in=True,
                                            refusal="registered" if taken else None)
                if reason is None:
                    try:
                        made = c.identity.register_terminal(
                            token, client_id, authorization_id=authorization, name=name,
                            machine=machine, after=head)
                    except TooManyTerminals:  # a 16th landed since the door; its step_up commits
                        return _json(429, {"error": "too_many_terminals"})
        if reason is not None:
            return first()
        if made is None:  # the caller's grant changed since the door, or the authorization is spent
            d.probe(token, client_id)
            return refusal()
        return _json(200, {"terminal": terminal(made, c.identity.terminal_last_seen([made]))})

    @app.delete("/v1/terminals/{client_id}")
    async def end_terminal(request: Request, client_id: str):
        token: Token = request.state.token
        origin = origin_of(request)
        _only(request.query_params, {"sub"})
        sub = served(token, request.query_params.get("sub"))
        if sub is None:  # a caller who may not act here never makes the door read a body
            d.probe(token, client_id)
            return refusal()
        proof = presented(await optional_body(request))
        found = c.identity.registration(client_id, sub, "terminal")  # an agent's is not one
        if found is None or found["revoked"]:
            d.probe(token, client_id)
            return refusal()
        # As for an agent: ending your own terminal, or the terminal ending itself with its
        # person's token, is never gated; ending one that serves someone else is, bound to the
        # pair, and a terminal's token concludes no second leg (identity.md §5).
        gated = sub != token.sub
        binding = {"act": "terminal.revoke", "subject": client_id, "destination": sub,
                   "delta": [], "origin": origin}

        def first() -> Response:  # the terminal it ends; the name is the terminal's own claim
            return first_leg(token, **binding, revokes={"terminal": {
                "client_id": client_id, "name": found["name"], "sub": sub}})

        if gated and proof is None:
            return first()
        revoked, reason = False, None
        with c.backend.atomic():
            if not gated or grantor(c.identity.refresh(token)):
                if gated:
                    reason = c.confirm.conclude(token, proof, **binding, fresh_sign_in=True)
                if reason is None:
                    revoked = c.identity.revoke_terminal(client_id, sub, actor=token.owner,
                                                         principal=token.principal)
        if reason is not None:
            return first()
        if not revoked:  # the caller's grant or the registration changed since the door
            d.probe(token, client_id)
            return refusal()
        return _json(200, {"result": "revoked"})

    @app.get("/v1/terminals/{client_id}/log")
    async def terminal_log(request: Request, client_id: str):
        token: Token = request.state.token
        params = request.query_params
        _only(params, {"sub", "limit"})
        limit = log_limit(params)
        sub = served(token, params.get("sub"))
        # An ended terminal's log stays readable; an agent's client id names no terminal here.
        if sub is None or c.identity.registration(client_id, sub, "terminal") is None:
            d.probe(token, client_id)
            return refusal()
        person = principal_id(None, sub)

        def own(ref: str | None) -> bool:
            # §4.3: what a terminal did to its person's other access shows in its log, judged
            # against the person it serves: their own `sub`, a registration serving them, of
            # either kind, live or ended, or an upload of theirs.
            if ref is None:
                return False
            if ref == sub or c.backend.get_agent_registration(ref, sub) is not None:
                return True
            upload = c.backend.get_upload(ref)
            return upload is not None and opener_of(upload["principal"], upload["actor"]) == person

        lines, positions, withheld = log_of(token, c.identity.terminal_acted(client_id, sub),
                                            limit, own)
        # `withheld`, on the record only. The terminal is named under its own key: `terminal`
        # here would read as this read having come through it (identity.md §3a).
        c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                        client=token.client, subject=client_id, read="terminal_log", items=[],
                        layers=[], withheld=withheld,
                        registration={"client_id": client_id, "sub": sub}, entries=positions)
        return _json(200, {"entries": lines})

    # -- confirm credentials (§4.3) -------------------------------------------------------------
    def whose(token: Token, sub: str | None) -> str | None:
        """The person a credential route acts on: the caller, or with `sub` another person, which
        only an admin over the whole container may name. None is §3's refusal."""
        if sub is None or f"user:{sub}" == person_of(token):
            return person_of(token)
        if token.has("admin") and "*" in token.scopes:
            return f"user:{sub}"
        return None

    def wire(cred: dict[str, Any]) -> dict[str, Any]:
        return {k: cred[k] for k in ("id", "name", "created_at", "last_used")}

    @app.get("/v1/credentials")
    async def credentials(request: Request):
        token: Token = request.state.token
        _only(request.query_params, {"sub"})
        person = whose(token, request.query_params.get("sub")) if (
            token.principal == "interactive") else None
        if person is None:
            d.probe(token, "credentials")
            return refusal()
        creds = c.confirm.credentials(person)
        c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                        client=token.client, read="credentials", items=[], layers=[],
                        withheld=0)
        return _json(200, {"credentials": [wire(x) for x in creds]})

    @app.post("/v1/credentials")
    async def register(request: Request):
        token: Token = request.state.token
        _only(request.query_params, set())
        origin = origin_of(request)
        if at_terminal(token):  # kept from a browser, so never a body read from a terminal
            d.probe(token, "credentials")
            return refusal()
        body = await optional_body_of(request, {"challenge", "attestation", "confirm", "name"})
        if token.principal != "interactive" or origin is None:
            d.probe(token, "credentials")
            return refusal()
        raw = _str(body.get("name"), optional=True, limit=CREDENTIAL_NAME_MAX)
        try:
            name = display_name(raw, limit=CREDENTIAL_NAME_MAX) if raw else "this device"
        except ValueError as e:
            raise Invalid from e
        if "challenge" not in body:
            if "attestation" in body or "confirm" in body:
                raise Invalid
            return registration(token, origin, name)
        challenge = _str(body["challenge"])
        proof = presented(body)
        # A fresh sign-in is a provider token's, from its `amr`: a container `Token` carries none,
        # and this door is never the owner's own surface (rest.md §4.3; a1r on #290).
        fresh = c.confirm.fresh(token)
        with c.backend.atomic():
            cred, reason = c.confirm.finish_registration(
                token, origin=origin, challenge_id=challenge, attestation=body.get("attestation"),
                presented=proof, name=name, fresh=fresh, owner_surface=False)
        if reason is not None:
            return registration(token, origin, name)
        return _json(200, {"credential": wire(cred)})

    def registration(token: Token, origin: str, name: str) -> Response:
        """A registration's first leg, fresh after a refusal too. Where its assertion options list
        the person's credentials, that is a read, and appends one (rest.md §4.3)."""
        out = c.confirm.begin_registration(token, origin=origin, name=name)
        if out["confirm"]["webauthn"] is not None:
            c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                            client=token.client, read="credentials", items=[], layers=[],
                            withheld=0)
        return _json(200, out)

    async def optional_body_of(request: Request, allowed: set[str]) -> dict[str, Any]:
        if not await request.body():
            return {}
        return await _object(request, allowed, set())

    @app.delete("/v1/credentials/{credential_id}")
    async def remove(request: Request, credential_id: str):
        token: Token = request.state.token
        _only(request.query_params, {"sub"})
        origin = origin_of(request)
        if at_terminal(token):  # removed from a browser, so never a body read from a terminal
            d.probe(token, credential_id)
            return refusal()
        proof = presented(await optional_body_of(request, {"confirm"}))
        person = whose(token, request.query_params.get("sub")) if (
            token.principal == "interactive") else None
        cred = c.backend.get_credential(credential_id)
        if person is None or cred is None or cred["removed"] or cred["person"] != person:
            d.probe(token, credential_id)
            return refusal()
        if proof is None:
            return first_leg(
                token, act="credential.remove", subject=credential_id, destination=None,
                delta=[], origin=origin
            )
        removed = False
        with c.backend.atomic():
            # A biometric proof only, never the button: the caller's own (rest.md §4.3).
            reason = c.confirm.conclude(token, proof, act="credential.remove",
                                        subject=credential_id, destination=None, delta=[],
                                        origin=origin, biometric_only=True)
            # Removed as it stands under the lock, never a snapshot read before it (a6 on #290).
            current = c.backend.get_credential(credential_id)
            if reason is None and current is not None and not current["removed"]:
                c.confirm.remove(token, current)
                removed = True
            else:
                # §4.3's closed set for a removal: the confirm's own reasons, mapped onto it.
                c.ledger.append("identity.credential", actor=token.owner,
                                principal=token.principal, subject=cred["person"], op="remove",
                                outcome="refused", reason=REMOVE_REASONS.get(reason, "stale"),
                                credential=credential_id)
        if not removed:
            return first_leg(
                token, act="credential.remove", subject=credential_id, destination=None,
                delta=[], origin=origin
            )
        return _json(200, {"result": "removed"})

    # -- BlobGrant redemption (§6): the descriptor is the credential ------------------------------
    @app.get("/v1/blobs/{sha256}")
    async def pull(request: Request, sha256: str):
        address = request.client.host if request.client else None
        data = redeem(c, d.throttle, address, sha256, request.query_params)
        # One chunk, read whole by `BlobStore.get`; streamed so that no Content-Length joins §6's
        # six headers.
        return refusal() if data is None else StreamingResponse(iter((data,)), headers=PULL_HEADERS)

    # -- MCP over Streamable HTTP (identity.md §7): stateless, so POST is all it declares ---------
    app.add_route(MCP_PATH, mcp, methods=["POST"], include_in_schema=False)

    # -- everything else ------------------------------------------------------------------------
    @app.api_route("/{rest:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"],
                   include_in_schema=False)
    async def undeclared(request: Request, rest: str):
        return refusal()

    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException

    @app.exception_handler(HTTPException)
    async def no_framework_shape(request: Request, exc: HTTPException):
        return refusal()  # a 405 would confirm the path exists (§3)

    @app.exception_handler(RequestValidationError)
    async def no_validation_shape(request: Request, exc: RequestValidationError):
        return invalid()

    return app
