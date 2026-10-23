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
artifact arrives through an upload (§4.4): open, bytes, item. The grant routes (§4.3) and
`BlobGrant` redemption (§6) land with their own code; until then those paths are undeclared and
answer §3's refusal, like any other.
"""

from __future__ import annotations

import asyncio
import calendar
import contextlib
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, Request
from starlette.responses import Response

from egzos.api.throttle import Throttle, throttle_key
from egzos.confirm import CREDENTIAL_NAME_MAX, FRESH_SIGN_IN_SECONDS, REMOVE_REASONS, person_of
from egzos.container import Container
from egzos.identity import GrantToken, display_name
from egzos.ledger import acting_for
from egzos.model import CONTAINER_TYPES, KINDS, VERIFIED_ONLY_KINDS, Node, Token
from egzos.store.find import QueryError, find, parse, shown
from egzos.store.items import StoreError
from egzos.store.nodes import AmbiguousRef, StructureError
from egzos.store.uploads import TooManyUploads, valid_open
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


def _json(status: int, payload: Any, extra: dict[str, str] | None = None) -> Response:
    body = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode()
    return Response(body, status_code=status, media_type="application/json",
                    headers={**HEADERS, **(extra or {})})


def refusal() -> Response:
    """§3's one refusal: absent, uncovered, lacking the capability, unserved, undeclared."""
    return _json(404, {"error": "not_found"})


def unauthorized() -> Response:
    """§2 item 5: every unauthenticated case, byte-identical."""
    return _json(401, {"error": "unauthorized"}, {"WWW-Authenticate": "Bearer"})


def invalid() -> Response:
    """§3: a request that fails on a fact identical for every container."""
    return _json(400, {"error": "invalid_request"})


def ambiguous(paths: list[str]) -> Response:
    return _json(409, {"error": "ambiguous", "matches": sorted(paths)})


def admin_over_all(token: Token) -> bool:
    """`admin` over `["*"]`, held by a person: the one form of that check at this door."""
    return token.principal == "interactive" and token.has("admin") and "*" in token.scopes


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
    if not isinstance(body, dict) or set(body) - allowed or required - set(body):
        raise Invalid
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
        """A covered node, or None for absent and uncovered alike. Raises `AmbiguousRef`."""
        if ref is None:
            return self.start(token)
        node = self.c.nodes.resolve_ref(ref, token)
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


def create_app(container: Container, *, door: Door | None = None) -> FastAPI:
    d = door or Door(container)
    c = container

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        async def closer() -> None:
            while True:
                await asyncio.sleep(CLOSE_EVERY_SECONDS)
                with contextlib.suppress(Exception):  # a closer that fails tries next round
                    d.throttle.close()

        task = asyncio.create_task(closer())
        try:
            yield
        finally:
            task.cancel()

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
            response.headers.update(cors)
            return response

        path = request.url.path
        if request.method == "OPTIONS":
            # identity.md §6: a preflight from an allowed origin gets 204 on every /v1/ path,
            # declared or not; from any other origin, §3's refusal and no CORS header.
            if cors and path.startswith("/v1/"):
                return out(Response(status_code=204, headers=HEADERS))
            return refusal()
        address = request.client.host if request.client else None
        if d.throttle.holds(address):
            d.throttle.count(address, refused=True)
            return out(unauthorized())
        token = d.caller(request.headers.get("authorization"))
        if token is None:
            d.throttle.count(address, refused=False)
            return out(unauthorized())
        request.state.token = token
        with acting_for(getattr(token, "acting_for", None)):
            try:
                response = await call_next(request)
            except Exception:  # noqa: BLE001 — never a stack, a path or an exception's text
                response = _json(500, {"error": "internal"})
        return out(response)

    @app.exception_handler(Invalid)
    async def on_invalid(request: Request, exc: Invalid):
        return invalid()

    @app.exception_handler(AmbiguousRef)
    async def on_ambiguous(request: Request, exc: AmbiguousRef):
        # §3: the matches named are only nodes the token covers; the refusal is a read too.
        d.probe(request.state.token, None)
        return ambiguous(exc.paths)

    # -- reads ----------------------------------------------------------------------------------
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
                {k: e[k] for k in ("item", "layer", "layer_type", "shadowed_by")}
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
        return _json(200, d.entry(found.to_dict(), node))

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
        orphans = c.uploads.orphans(token, admin=admin_over_all(token))
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
        if not c.uploads.discard(token, upload_id, admin=admin_over_all(token)):
            d.probe(token, upload_id)
            return refusal()
        return _json(200, {"result": "discarded"})

    @app.post("/v1/scopes")
    async def make(request: Request):
        token: Token = request.state.token
        _only(request.query_params, set())
        body = await _object(request, {"type", "name", "parent"}, {"type", "name"})
        kind = _str(body["type"], limit=32)
        name = _str(body["name"], limit=255)
        if kind not in _CREATABLE:
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
        return _json(200, {"node": d.node(node)})

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
                  delta: list[dict[str, Any]], origin: str | None) -> Response:
        newly = names(delta)
        # Showing who would newly see an item is a read of credential metadata (§4.2 item 2).
        c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                        client=token.client, subject=subject, items=[], layers=[], withheld=0,
                        confirm_for=act, newly=newly)
        return _json(200, c.confirm.issue(token, act=act, subject=subject,
                                          destination=destination,
                                          delta=[m["token"] for m in delta], newly=newly,
                                          origin=origin))

    def presented(body: dict[str, Any]) -> dict[str, Any] | None:
        value = body.get("confirm")
        if value is None:
            return None
        if (not isinstance(value, dict) or set(value) - {"challenge", "proof", "assertion"}
                or not isinstance(value.get("challenge"), str)
                or value.get("proof") not in ("biometric", "button")):
            raise Invalid
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
        auth_time = token.auth_time if isinstance(token, GrantToken) else None
        fresh = auth_time is not None and c.confirm.clock() - auth_time <= FRESH_SIGN_IN_SECONDS
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
