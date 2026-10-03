# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The lifeboat (spec/design/lifeboat.md): `egzos web` — FastAPI + Jinja + htmx, server-rendered,
in-process with the container, loopback only, no JS toolchain, tokens as CSS variables only.

Pages: home / search (`/`), item detail (`/items/<id>`), the scheme switch (`/prefs`), the uniform
not-found page, and — rendered to the tap spec's L column (lifeboat.md R11) — the pending pages
(`/pending`, `/pending/<id>`) and the tap page (`/tap/<token>`).

The session: the URL opened at launch carries a per-launch key; the first visit trades it for an
HttpOnly, SameSite=Strict cookie that every request then needs. Every POST also carries the key as
a form field and must name this origin (a missing Origin is refused). The lifeboat is the owner's:
it is served to the interactive principal only (lifeboat.md §14.6).

Every page is an audited read (`context.fetch`), the not-found paths included. Human-only acts take
two presses with a server-signed `arm` valid 10 s; promoting an item then asks the container, which
passes an open window or redirects to `/tap/<token>`; the pending page embeds the tap block itself
(the tap spec §3.2). Every decision appends `step_up`.

Not here yet, named: blob grants (`blob.grant` is decided, not running — F5), so artifacts offer a
Download that pulls through `ItemStore.blob_pull` (audited `blob.pull`) and no inline image/PDF
preview; search relevance order (the grammar returns recency only).
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from datetime import UTC, datetime
from importlib import resources
from typing import Any
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from egzos.authz.presence import (
    ARM_SECONDS,
    Presence,
    Tap,
    build_act,
    presence_text,
    tap_timeout,
    window_seconds,
)
from egzos.container import OWNER, Container
from egzos.store.find import QueryError, find
from egzos.trust import TrustError
from egzos.web.strings import S, t

COOKIE = "egzos_k"
SCHEME_COOKIE = "egz-scheme"
SCHEMES = {
    "light": {"scheme": "light", "canvas": None},
    "dark-neutral": {"scheme": "dark", "canvas": "neutral"},
    "dark-violet": {"scheme": "dark", "canvas": "violet"},
}
PAGE = 50  # lifeboat.md §5
BODY_CUT = 4000
REASON_CUT = 480
CHIPS = 6
ROWS = 12
TEXT_KINDS = {"memory", "preference", "skill", "integration", "alias", "rule"}
_UNRESERVED = re.compile(r"[A-Za-z0-9\-._~]+")

_TEMPLATES = Jinja2Templates(directory=str(resources.files("egzos.web").joinpath("templates")))


# --- formats (lifeboat.md §5) ----------------------------------------------------------------------
def short_id(i: str) -> str:
    return f"{i[:8]} … {i[-4:]}" if len(i) > 12 else i


def clock(iso: str | None) -> str:
    try:
        return (
            datetime.strptime(iso or "", "%Y-%m-%dT%H:%M:%SZ")
            .replace(tzinfo=UTC)
            .astimezone()
            .strftime("%H:%M:%S")
        )
    except ValueError:
        return ""


def age(iso: str | None) -> str:
    try:
        then = datetime.strptime(iso or "", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()
    except ValueError:
        return ""
    secs = max(0, int(time.time() - then))
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60} min ago"
    if secs < 86400:
        return f"{secs // 3600} h ago"
    return f"{secs // 86400} d ago"


def since(ts: float) -> str:
    t_ = datetime.fromtimestamp(ts).astimezone()
    off = t_.strftime("%z") or "+0000"
    sign = "−" if off[0] == "-" else "+"
    return f"{t_.strftime('%H:%M')} (UTC{sign}{off[1:3]}:{off[3:5]})"


def size(n: int | None) -> str:
    if n is None:
        return S["prov.null"]
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n} B"


def item_title(item) -> str:
    c = item.content or {}
    return c.get("auto_title") or c.get("title") or item.key or S["row.untitled"]


def return_target(value: str | None) -> str:
    """consent.md D-C5, the four steps: reject before parsing; match the parsed path exactly against
    `/` · `/items/<id>` · `/pending` · `/pending/<id>`; carry the query (still encoded) only to `/`;
    anything else is `/`."""
    v = value or ""
    if (
        not v.startswith("/")
        or v.startswith("//")
        or v.startswith("/\\")
        or "\\" in v
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in v)
    ):
        return "/"
    parts = urlsplit(v)
    path = parts.path
    if path == "/":
        return "/" + (f"?{parts.query}" if parts.query else "")
    if path == "/pending":
        return path
    for prefix in ("/items/", "/pending/"):
        if path.startswith(prefix):
            ident = path[len(prefix) :]
            if _UNRESERVED.fullmatch(ident) and ident not in (".", ".."):
                return path
    return "/"


class Lifeboat:
    """Request handling, independent of the socket server so tests drive it through TestClient."""

    def __init__(self, container: Container, *, key: str | None = None, host: str = "127.0.0.1"):
        self.c = container
        self.key = key or secrets.token_urlsafe(32)
        self.host = host
        self.since = time.time()
        self.presence = Presence(container)
        self.taps: dict[str, dict[str, Any]] = {}  # token → {tap, return}
        self.outcomes: dict[str, tuple[str, str]] = {}  # subject → (state, text), shown once

    # -- arming: a server-signed token, valid 10 s (the tap spec §18; lifeboat.md §18) -------------
    def _sig(self, purpose: str, ref: str, version: object, deadline: int) -> str:
        msg = f"{purpose}|{ref}|{version}|{deadline}".encode()
        return hmac.new(self.key.encode(), msg, hashlib.sha256).hexdigest()

    def arm(self, purpose: str, ref: str, version: object) -> str:
        deadline = int(time.time()) + ARM_SECONDS
        return f"{deadline}.{self._sig(purpose, ref, version, deadline)}"

    def armed(self, purpose: str, ref: str, version: object, token: str | None) -> bool:
        try:
            deadline_s, sig = (token or "").split(".", 1)
            deadline = int(deadline_s)
        except ValueError:
            return False
        return deadline >= time.time() and hmac.compare_digest(
            sig, self._sig(purpose, ref, version, deadline)
        )

    # -- cursors: opaque, signed, carrying no scope or count in the clear (§15) ---------------------
    def cursor(self, q: str, offset: int) -> str:
        sig = hmac.new(self.key.encode(), f"cursor|{q}|{offset}".encode(), hashlib.sha256)
        return f"{offset:x}.{sig.hexdigest()[:24]}"

    def offset(self, q: str, cursor: str | None) -> int:
        try:
            off_s, sig = (cursor or "").split(".", 1)
            off = int(off_s, 16)
        except ValueError:
            return 0
        good = hmac.new(self.key.encode(), f"cursor|{q}|{off}".encode(), hashlib.sha256)
        return off if hmac.compare_digest(sig, good.hexdigest()[:24]) else 0  # R5: first page

    # -- reads ------------------------------------------------------------------------------------
    def token(self):
        return self.c.require_token()

    def pending_count(self) -> int:
        return len(self.c.backend.list_proposals(status="open"))

    def read(self, view: str, **details: Any) -> None:
        """Every page is a read: one `context.fetch`, the nav's pending count included."""
        token = self.token()
        self.c.ledger.append(
            "context.fetch",
            actor=OWNER,
            principal=token.principal,
            subject=details.pop("subject", None),
            scope=details.pop("scope", None),
            client="web",
            view=view,
            pending_count=self.pending_count(),
            layers=details.pop("layers", []),
            withheld=0,
            **details,
        )

    def shell(self, request: Request, *, current: str | None, nav: bool = True,
              scheme: bool = True, here: str | None = None) -> dict[str, Any]:
        n = self.pending_count()
        status = self.presence.window_status()
        window = None
        if status and status["state"] == "open":
            pair = status.get("pair") or ["?", "?"]
            window = {"state": "open", "text": t("shell.window", source=pair[0],
                                                 destination=pair[1],
                                                 closes=clock(status["closes"]))}
        elif status:
            window = {"state": "lapsed", "text": t("shell.lapsed", at=clock(status["at"]))}
        if here is None:
            here = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        return {
            "container_line": t("shell.container", name=self.c.home.name, host=self.host),
            "viewer_line": t("shell.viewer", user=OWNER, since=since(self.since)),
            "nav": (
                [
                    {"href": "/", "label": S["nav.search"], "current": current == "search"},
                    {
                        "href": "/pending",
                        "label": t("nav.pending", n=n) if n else S["nav.pending.zero"],
                        "current": current == "pending",
                    },
                ]
                if nav
                else None
            ),
            "scheme": (
                {"current": self.scheme_of(request), "return": here, "csrf": self.key}
                if scheme
                else None
            ),
            "window": window,
        }

    @staticmethod
    def scheme_of(request: Request) -> str | None:
        value = request.cookies.get(SCHEME_COOKIE)
        return value if value in SCHEMES else None  # R10: an invalid value is no cookie

    def render(self, request: Request, template: str, context: dict[str, Any],
               status: int = 200) -> HTMLResponse:
        scheme = SCHEMES.get(self.scheme_of(request) or "")
        return _TEMPLATES.TemplateResponse(
            request,
            template,
            {
                "S": S,
                "t": t,
                "scheme": scheme,
                "printed": time.strftime("%H:%M:%S"),
                "container_name": self.c.home.name,
                **context,
            },
            status_code=status,
        )

    def not_found(self, request: Request) -> HTMLResponse:
        """R12: one page for not-found, not-yours, tombstoned, quarantined and malformed ids."""
        self.read("not-found")
        return self.render(
            request,
            "notfound.html",
            # R12: one page for five causes — nothing on it depends on what was asked for.
            {"shell": self.shell(request, current=None, here="/"), "title": S["title.notfound"]},
            status=404,
        )

    # -- the decision, shared by the pending page and the lifeboat-hosted tap ---------------------
    def decide(self, act: dict[str, Any], outcome: str, *, windowed: bool, via: str) -> str:
        token = self.token()
        at = time.strftime("%H:%M:%S")
        closes = self.presence.record(act, via=via, outcome=outcome, windowed=windowed)
        try:
            if outcome == "denied":
                if act["kind"] == "proposal":
                    self.c.trust.deny(act["subject"], token=token, actor=OWNER)
                    return t("outcome.denied", at=at, user=OWNER, destination=act["dest"])
                return t("tap.invalid")
            if outcome not in ("approved", "window"):
                return t("tap.invalid")
            if act["kind"] == "proposal":
                p = self.c.trust.execute(act["subject"], token=token, actor=OWNER)
                landed = {i.status for i in (self.c.backend.get(x) for x in p["items"]) if i}
                trust = ", ".join(sorted(landed)) or "unverified"
                if closes:
                    return t("outcome.approved", at=at, user=OWNER, n=len(p["items"]),
                             destination=act["dest"], trust=trust, closes=clock(closes))
                return t("outcome.approved.nowindow", at=at, user=OWNER, n=len(p["items"]),
                         destination=act["dest"], trust=trust)
            item = self.c.backend.get(act["subject"])
            if item is None or item.status != "unverified":
                raise TrustError("no longer pending")
            self.c.trust.promote(item, token=token, actor=OWNER)
            return t("act.promoted", at=at, user=OWNER)
        except TrustError as e:
            # Presence was proven and the act was refused: on the chain, and the window that
            # signature opened closes with it — as the CLI does (presence.act_failed).
            self.presence.act_failed(act, e, reason="refused")
            return t("outcome.invalid") if act["kind"] == "proposal" else t("tap.invalid")
        except Exception as e:
            # The act rolled back whole; the chain says so and the signature's window closes.
            self.presence.act_failed(act, e)
            raise

    def sweep(self) -> None:
        """A tap left undecided past its timeout expires, and says so on the record."""
        for token, entry in list(self.taps.items()):
            tap = entry["tap"]
            if tap.outcome is None and time.time() - tap.opened > tap_timeout():
                self.presence.record(tap.act, via="tap", outcome="expired")
                del self.taps[token]


def who_wrote(item) -> str:
    """Principals as §5 renders them: an agent by `agent:<client>`, the owner as `you`."""
    prov = item.provenance or {}
    return f"agent:{prov.get('client')}" if prov.get("principal") == "client" else "you"


def create_app(boat: Lifeboat, origin: str) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    static = resources.files("egzos.web")

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        # Every refusal before the session is proven is the same static page: no shell, no
        # container state, nothing written to the chain. Only the bound host is served, so a
        # page elsewhere that rebinds a name to 127.0.0.1 reaches nothing.
        if request.headers.get("host") != boat.host:
            return _harden(HTMLResponse(_LOCKED, status_code=403), path)
        key = request.query_params.get("k")
        if request.method == "GET" and key is not None:
            if secrets.compare_digest(key, boat.key):
                resp: Response = RedirectResponse(path or "/", status_code=303)
                resp.set_cookie(COOKIE, boat.key, httponly=True, samesite="strict", path="/")
                return _harden(resp, path)
            return _harden(HTMLResponse(_LOCKED, status_code=403), path)
        if not secrets.compare_digest(request.cookies.get(COOKIE, ""), boat.key):
            return _harden(HTMLResponse(_LOCKED, status_code=403), path)
        if request.method == "POST":
            # A missing Origin is refused too: every browser sends one on a form POST.
            if request.headers.get("origin") != origin:
                return _harden(HTMLResponse(_REFUSED, status_code=403), path)
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001 — R12: never a code, path or exception text
            response = boat.render(request, "error.html",
                                   {"shell": boat.shell(request, current=None),
                                    "title": S["title.notfound"],
                                    "retry": str(request.url.path)}, status=500)
        return _harden(response, path)

    async def form_of(request: Request) -> dict[str, str] | None:
        form = {k: str(v) for k, v in (await request.form()).items()}
        if not secrets.compare_digest(form.get("csrf", ""), boat.key):
            return None
        return form

    # -- static: the one stylesheet, the token file, htmx (vendored) -------------------------------
    @app.get("/static/{name}")
    async def static_file(request: Request, name: str):
        files = {
            "tokens.css": ("tokens.css", "text/css; charset=utf-8"),
            "lifeboat.css": ("static/lifeboat.css", "text/css; charset=utf-8"),
            "htmx.min.js": ("static/htmx.min.js", "text/javascript; charset=utf-8"),
        }
        if name not in files:
            return boat.not_found(request)
        rel, ctype = files[name]
        return Response(static.joinpath(rel).read_bytes(), media_type=ctype)

    # -- home / search (lifeboat.md §2, R2–R5) ------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request, q: str = "", cursor: str | None = None):
        token = boat.token()
        invalid = False
        try:
            hits = find(boat.c, token, q)
        except QueryError:
            hits, invalid = [], True
        start = boat.offset(q, cursor)
        if start >= len(hits):
            start = 0
        page = hits[start : start + PAGE]
        boat.read("search", query=q or None, items=[i.id for _, i in page])
        rows = []
        for node, item in page:
            path = boat.c.nodes.path(node)
            rows.append({
                "id": item.id,
                "kind": item.kind,
                "title": item_title(item),
                "untitled": item_title(item) == S["row.untitled"],
                "scope": path,
                "status": item.status,
                "age": age(item.lifecycle.get("updated_at")),
                "updated": item.lifecycle.get("updated_at"),
                "who": who_wrote(item),
                "version": item.lifecycle.get("version", 1),
                "tags": item.tags or [],
            })
        if invalid:
            header = None
        elif not hits:
            header = S["results.uncounted"] if q else "Recent"
        else:
            header = t("results.count", n=len(hits)) if q else t("results.recent", n=len(hits))
        nxt = boat.cursor(q, start + PAGE) if start + PAGE < len(hits) else None
        return boat.render(request, "home.html", {
            "shell": boat.shell(request, current="search"),
            "title": S["title.home"],
            "q": q,
            "invalid": invalid,
            "header": header,
            "rows": rows,
            "empty": not invalid and not hits,
            "next": f"/?{urlencode({'q': q, 'cursor': nxt})}" if nxt else None,
        })

    # -- item detail (lifeboat.md §3, R6–R9) ------------------------------------------------------
    def item_or_none(item_id: str):
        token = boat.token()
        if not _UNRESERVED.fullmatch(item_id or ""):
            return None, None
        item = boat.c.backend.get(item_id)
        node = boat.c.backend.get_node(item.scope) if item else None
        if (
            not item
            or not node
            or item.status == "quarantined"
            or item.lifecycle.get("tombstoned")
            or not boat.c.trust.covers(token, node)
        ):
            return None, None
        return item, node

    def item_context(request: Request, item, node, *, full: bool, arm: str | None,
                     message: tuple[str, str] | None) -> dict[str, Any]:
        content = item.content or {}
        body = content.get("body") or content.get("inline") or ""
        cut = (not full) and len(body) > BODY_CUT
        path = boat.c.nodes.path(node)
        derived = (item.provenance or {}).get("derived_from")
        derived_link = None
        if derived:
            d_item = boat.c.backend.get(derived)
            d_node = boat.c.backend.get_node(d_item.scope) if d_item else None
            if (d_item and d_node and d_item.status != "quarantined"
                    and boat.c.trust.covers(boat.token(), d_node)):
                derived_link = derived
        trust = item.trust or {}
        prov = item.provenance or {}
        return {
            "shell": boat.shell(request, current=None),
            "title": S["title.item"],
            "item": item,
            "ref": t("item.ref", id=short_id(item.id), kind=item.kind,
                     version=item.lifecycle.get("version", 1)),
            "heading": item_title(item),
            "untitled": item_title(item) == S["row.untitled"],
            "scope": path,
            "ring": None if node.type in ("user", "global") else node.type,
            "engine": content.get("title_engine"),
            "text_kind": item.kind in TEXT_KINDS,
            "body": body[:BODY_CUT] if cut else body,
            "cut": cut,
            "artifact": {
                "filename": content.get("filename"),
                "size": size(content.get("size")),
                "mime": content.get("mime") or S["prov.null"],
                "sha": (f"sha256 {content['sha256'][:4]}…{content['sha256'][-4:]}"
                        if content.get("sha256") else S["prov.null"]),
            } if item.kind == "artifact" else None,
            "prov": [
                ("actor", prov.get("actor")),
                ("principal", prov.get("principal")),
                ("client", prov.get("client")),
                ("derived from", derived),
                ("imported from", prov.get("imported_from")),
                ("approved by", prov.get("approved_by")),
            ],
            "derived_link": derived_link,
            "promoted": (t("trust.promoted", at=clock(trust.get("promoted_at")),
                           prefix=(trust.get("manifest") or "")[:8])
                         if item.status == "verified" and trust.get("promoted_at") else None),
            "life": [
                ("created", clock(item.lifecycle.get("created_at")) or S["prov.null"]),
                ("updated", clock(item.lifecycle.get("updated_at")) or S["prov.null"]),
                ("version", f"v{item.lifecycle.get('version', 1)}"),
            ],
            "tags": item.tags or [],
            "key": item.key,
            "can_promote": item.status == "unverified",
            "arm": arm,
            "version": item.lifecycle.get("version", 1),
            "csrf": boat.key,
            "message": message,
        }

    @app.get("/items/{item_id}", response_class=HTMLResponse)
    async def item_page(request: Request, item_id: str, full: int = 0):
        item, node = item_or_none(item_id)
        if item is None:
            return boat.not_found(request)
        boat.read("item", subject=item.id, scope=item.scope, items=[item.id], layers=[node.id])
        message = boat.outcomes.pop(item.id, None)
        return boat.render(request, "item.html",
                           item_context(request, item, node, full=bool(full), arm=None,
                                        message=message))

    @app.post("/items/{item_id}/promote", response_class=HTMLResponse)
    async def promote(request: Request, item_id: str):
        form = await form_of(request)
        if form is None:
            return HTMLResponse(_REFUSED, status_code=403)
        item, node = item_or_none(item_id)
        if item is None:
            return boat.not_found(request)
        version = item.lifecycle.get("version", 1)
        if str(form.get("version")) != str(version):
            boat.read("item", subject=item.id, scope=item.scope, items=[item.id])
            return boat.render(request, "item.html", item_context(
                request, item, node, full=False, arm=None,
                message=("invalid", S["act.invalid"])))
        if not boat.armed("promote", item.id, version, form.get("arm")):
            # The first press — or a confirm whose 10 s lapsed — arms in place (R9 confirming).
            boat.read("item", subject=item.id, scope=item.scope, items=[item.id])
            ctx = item_context(request, item, node, full=False,
                               arm=boat.arm("promote", item.id, version), message=None)
            return boat.render(request, "item.html", {**ctx, "refresh": ARM_SECONDS})
        act = build_act(boat.c, item.id)
        if act is None:
            return boat.not_found(request)
        if boat.presence.covers(act):
            boat.outcomes[item.id] = ("approved",
                                      boat.decide(act, "window", windowed=False, via="window"))
            return RedirectResponse(f"/items/{item.id}", status_code=303)
        # Step-up required: a one-shot tap, its return bound now (the tap spec D-T9 (a)).
        boat.sweep()

        def perform(outcome: str, windowed: bool) -> str:
            # Runs inside the tap's own request: the container answers before anything is shown.
            text = boat.decide(act, outcome, windowed=windowed, via="tap")
            boat.outcomes[act["subject"]] = (outcome, text)
            return text

        tap = Tap(act, container=boat.c.home.name, host=boat.host, decide=perform)
        boat.taps[tap.token] = {"tap": tap, "return": return_target(f"/items/{item.id}")}
        return RedirectResponse(f"/tap/{tap.token}", status_code=303)

    @app.get("/items/{item_id}/download")
    async def download(request: Request, item_id: str):
        item, node = item_or_none(item_id)
        token = boat.token()
        data = (boat.c.store.blob_pull(item, token=token, actor=OWNER, principal=token.principal)
                if item is not None and item.kind == "artifact" else None)
        if data is None:
            return boat.not_found(request)
        name = re.sub(r"[^A-Za-z0-9._-]", "_", (item.content or {}).get("filename") or item.id)
        return Response(data, media_type="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    # -- the tap, hosted here for the promote's step-up ----------------------------------------------
    @app.get("/tap/{token}", response_class=HTMLResponse)
    async def tap_get(request: Request, token: str):
        boat.sweep()
        entry = boat.taps.get(token)
        if not entry or not entry["tap"].live(f"/tap/{token}"):
            return HTMLResponse(_tap_empty(), status_code=404)
        status, page = entry["tap"].get()
        return HTMLResponse(page, status_code=status)

    @app.post("/tap/{token}", response_class=HTMLResponse)
    async def tap_post(request: Request, token: str):
        # Guarded by the session cookie, this origin's Origin, and in place of the form key the
        # tap's own path token: unguessable, single-use, bound at issue (the tap page is the
        # shared presence.Tap, which carries no lifeboat form key).
        boat.sweep()
        entry = boat.taps.get(token)
        if not entry or not entry["tap"].live(f"/tap/{token}"):
            return HTMLResponse(_tap_empty(), status_code=404)
        step = str((await request.form()).get("step", ""))
        tap = entry["tap"]
        status, page = tap.post(step)
        if tap.outcome is None:
            return HTMLResponse(page, status_code=status)
        # Decided: `perform` has run and parked the container's answer for the item page.
        del boat.taps[token]
        return RedirectResponse(entry["return"], status_code=303)

    # -- the pending pages (the tap spec §3, §4, §18 — L column) -----------------------------------
    def queue() -> list[dict[str, Any]]:
        rows = []
        for p in sorted(boat.c.backend.list_proposals(status="open"),
                        key=lambda p: p.get("created_at", "")):
            by = p.get("proposed_by") or {}
            rows.append({
                "id": p["id"],
                "label": S["kind.publish"],
                "title": f"{len(p['items'])} items · {p['from_path']} → {p['to_path']}",
                "meta": " · ".join(x for x in (
                    f"agent:{by['client']}" if by.get("principal") == "client" else "you",
                    age(p.get("created_at")),
                ) if x),
            })
        return rows

    def pending_context(request: Request, pid: str | None, *, arm: dict[str, str] | None,
                        message: tuple[str, str] | None) -> dict[str, Any] | None:
        rows = queue()
        open_id = pid or (rows[0]["id"] if rows else None)
        detail = None
        if open_id:
            act = build_act(boat.c, open_id)
            if act is None or act["kind"] != "proposal":
                if pid and message is None:
                    return None
            else:
                p = boat.c.backend.get_proposal(open_id)
                reason = act.get("reason") or ""
                audience = act.get("audience", [])
                people = sum(1 for a in audience if a.get("principal") == "interactive")
                seconds = window_seconds()
                detail = {
                    "id": open_id,
                    "ref": t("ref.proposal", id=short_id(open_id),
                             at=clock(p.get("created_at"))),
                    "title": t("title.move", n=len(act["items"]), source=act["from"],
                               destination=act["to"]),
                    "who": act.get("requester") or "you",
                    "reason": reason,
                    "reason_cut": reason[:REASON_CUT] if len(reason) > REASON_CUT else None,
                    "moves": act["items"][:ROWS],
                    "more_moves": act["items"][ROWS:],
                    "dest": act["dest"],
                    "count": t("audience.count", people=people, agents=len(audience) - people),
                    "chips": audience[:CHIPS],
                    "more_chips": audience[CHIPS:],
                    "consequence": act.get("consequence"),
                    "presence": presence_text(act, seconds),
                    "terms": (
                        f"window would close {time.strftime('%H:%M:%S', time.localtime(time.time() + seconds))}"
                        f" · org policy {seconds // 60}:{seconds % 60:02d} · close early at any time"
                        if seconds else None
                    ),
                    "nowindow": bool(seconds),
                    "blocked": act.get("blocked"),
                    "arm": arm,
                    "csrf": boat.key,
                }
        status = boat.presence.window_status()
        return {
            "shell": boat.shell(request, current="pending", scheme=False),
            "title": S["title.pending"],
            "rows": rows,
            "open_id": open_id,
            "detail": detail,
            "message": message,
            "window": status if status and status["state"] == "open" else None,
            "window_text": (t("window.open", closes=clock(status["closes"]))
                            if status and status["state"] == "open" else None),
        }

    @app.get("/pending", response_class=HTMLResponse)
    async def pending(request: Request):
        ctx = pending_context(request, None, arm=None, message=None)
        boat.read("pending", proposals=[r["id"] for r in ctx["rows"]])
        return boat.render(request, "pending.html", ctx)

    @app.get("/pending/{pid}", response_class=HTMLResponse)
    async def pending_one(request: Request, pid: str):
        message = boat.outcomes.pop(pid, None)
        ctx = pending_context(request, pid, arm=None, message=message)
        if ctx is None:
            return boat.not_found(request)
        boat.read("pending", subject=pid, proposals=[r["id"] for r in ctx["rows"]])
        return boat.render(request, "pending.html", ctx)

    @app.get("/pending/{pid}/window", response_class=HTMLResponse)
    async def pending_window(request: Request, pid: str):
        # Not an audited read, on purpose: the 15 s poll shows only the window line (open, and
        # when it closes), which the chain already holds as the step_up that opened it, and no
        # item. The page that embeds it is the audited read.
        status = boat.presence.window_status()
        text = (t("window.open", closes=clock(status["closes"]))
                if status and status["state"] == "open" else None)
        return boat.render(request, "_window.html", {"pid": pid, "window_text": text})

    @app.post("/pending/{pid}", response_class=HTMLResponse)
    async def pending_act(request: Request, pid: str):
        form = await form_of(request)
        if form is None:
            return HTMLResponse(_REFUSED, status_code=403)
        act = build_act(boat.c, pid)
        if act is None or act["kind"] != "proposal":
            return boat.not_found(request)
        step = form.get("step", "")
        if step == "deny":  # one press: deny is the safe direction
            boat.outcomes[pid] = ("denied", boat.decide(act, "denied", windowed=False,
                                                        via="lifeboat"))
            return RedirectResponse(f"/pending/{pid}", status_code=303)
        if act.get("blocked"):
            return RedirectResponse(f"/pending/{pid}", status_code=303)
        if step in ("arm", "arm_once"):
            mode = "once" if step == "arm_once" else "window"
            ctx = pending_context(request, pid, arm={"mode": mode,
                                                     "token": boat.arm(mode, pid, 0)},
                                  message=None)
            return boat.render(request, "pending.html", {**ctx, "refresh": ARM_SECONDS})
        mode = form.get("mode", "window")
        if step == "confirm" and mode in ("once", "window") and boat.armed(
            mode, pid, 0, form.get("arm")
        ):
            boat.outcomes[pid] = ("approved", boat.decide(
                act, "approved", windowed=mode == "window", via="lifeboat"))
            return RedirectResponse(f"/pending/{pid}", status_code=303)
        return RedirectResponse(f"/pending/{pid}", status_code=303)  # lapsed arm: un-armed

    # -- the scheme switch (R10) --------------------------------------------------------------------
    @app.post("/prefs")
    async def prefs(request: Request):
        form = await form_of(request)
        if form is None:
            return HTMLResponse(_REFUSED, status_code=403)
        resp = RedirectResponse(return_target(form.get("return")), status_code=303)
        value = form.get("scheme", "")
        if value in SCHEMES:
            resp.set_cookie(SCHEME_COOKIE, value, httponly=True, samesite="strict", path="/")
        return resp

    @app.api_route("/{rest:path}", methods=["GET", "POST"], include_in_schema=False)
    async def anything_else(request: Request, rest: str):
        return boat.not_found(request)

    return app


def _harden(resp: Response, path: str) -> Response:
    """lifeboat.md §18: every response is no-referrer, no-store, nosniff, framed by no one."""
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    # The tap page carries its own inline style (it is the same page the CLI serves); every other
    # page loads one stylesheet and one script, both from here.
    style = "'self' 'unsafe-inline'" if path.startswith("/tap/") else "'self'"
    resp.headers["Content-Security-Policy"] = (
        f"default-src 'none'; script-src 'self'; style-src {style}; img-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    )
    return resp


def _tap_empty() -> str:
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8><title>egzos · presence</title>"
        f"</head><body><main><h1>{S['tap.empty']}</h1></main></body></html>"
    )


_LOCKED = (
    "<!doctype html><html lang=en><head><meta charset=utf-8><title>egzos</title></head><body>"
    "<main><h1>Nothing here.</h1></main></body></html>"
)
_REFUSED = _LOCKED
