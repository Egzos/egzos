# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The lifeboat (spec/design/lifeboat.md): `egzos web` — FastAPI + Jinja + htmx, server-rendered,
in-process with the container, loopback only, no JS toolchain, tokens as CSS variables only.

Pages: home / search (`/`), item detail (`/items/<id>`), the scheme switch (`/prefs`), the uniform
not-found page, and — rendered to the tap spec's L column (lifeboat.md R11) — the pending pages
(`/pending`, `/pending/<id>`) and the tap page (`/tap/<token>`).

The session is three values, none of them in a URL after the first visit: a launch key that works
once (the first visit trades it for the session); the session itself, an HttpOnly, SameSite=Strict
cookie that every request needs and no page carries; and a form key, a hidden field every POST
carries alongside the cookie and an exact Origin (a missing Origin is refused). The tap POST
carries its path token in place of the form key. A caller without the session gets one static
page and nothing on the chain. The lifeboat is the owner's: it is served to the interactive
principal only (lifeboat.md §14.6).

Every page the session sees is an audited read (`context.fetch`), the not-found page included.
Human-only acts take two presses: the first issues a server-held nonce, single-use, valid 10 s and
bound to the act, the item and its version; promoting an item then asks the container, which
passes an open window or redirects to `/tap/<token>`; the pending page embeds the tap block itself
(the tap spec §3.2). Every decision appends `step_up`.

Not here yet, named: blob grants (`blob.grant` is decided, not running — F5), so artifacts offer a
Download that pulls through `ItemStore.blob_pull` (audited `blob.pull`) and no inline image/PDF
preview; search relevance order (the grammar returns recency only).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import UTC, datetime
from importlib import resources
from typing import Any
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from egzos.authz.presence import (
    ARM_SECONDS,
    Presence,
    Tap,
    build_act,
    presence_text,
    tap_css,
    tap_timeout,
    window_seconds,
)
from egzos.container import OWNER, Container
from egzos.store.find import QueryError, find, shown
from egzos.trust import TrustError
from egzos.web.strings import S, around, number_free, t

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



def _same(given: str, held: str) -> bool:
    """Constant-time equality for caller-supplied text. `compare_digest` raises on a non-ASCII
    str, which would turn a forged key, cookie or cursor into a 500 instead of the one refusal;
    as UTF-8 bytes any text compares, and a mismatch is just False."""
    return secrets.compare_digest(given.encode("utf-8", "surrogatepass"), held.encode("utf-8"))


class Lifeboat:
    """Request handling, independent of the socket server so tests drive it through TestClient."""

    def __init__(self, container: Container, *, key: str | None = None, host: str = "127.0.0.1",
                 launch_host: str | None = None):
        self.c = container
        # Three values, none of which stands in for another:
        # - the launch key rides the URL once and is exchanged for a session, then is dead;
        # - the session is the HttpOnly cookie, and never appears in a page;
        # - the form key is in every page, and is never a credential on its own.
        # Cursors are signed with a secret that never leaves this process.
        #
        # Two hosts when `launch_host` is set (`egzos web` always sets it). A browser does not
        # isolate cookies by port, so a cookie for 127.0.0.1 would also reach any other server
        # on 127.0.0.1 the owner's browser visits. The session therefore lives on `host`, a
        # per-launch random `<label>.localhost`, minted here and never printed or put in argv:
        # the launch key is redeemed on `launch_host` (127.0.0.1), which answers only with a
        # single-use handoff to `host`, where the host-only cookie is set.
        self.key = key or secrets.token_urlsafe(32)
        self.redeemed = False
        self.launch_host = launch_host
        self._handoff: tuple[str, float] | None = None
        self.session = secrets.token_urlsafe(32)
        self.form_key = secrets.token_urlsafe(32)
        self._signing = secrets.token_bytes(32)
        # nonce → (purpose, ref, version, until, armed while a window covered the act)
        self._arms: dict[str, tuple[str, str, str, float, bool]] = {}
        self.host = host
        self.since = time.time()
        self.presence = Presence(container)
        self.taps: dict[str, dict[str, Any]] = {}  # token → {tap, return}
        self.outcomes: dict[str, tuple[str, str]] = {}  # subject → (state, text), shown once

    def hand_off(self) -> str:
        """The single-use value that carries the redeemed launch to the session host (10 s)."""
        token = secrets.token_urlsafe(32)
        self._handoff = (token, time.time() + ARM_SECONDS)
        return token

    def take_handoff(self, token: str) -> bool:
        held, self._handoff = self._handoff, None
        return bool(held) and _same(token, held[0]) and held[1] >= time.time()

    # -- arming: a server-held nonce, single-use, valid 10 s, bound to one act (the tap's model) ---
    def arm(self, purpose: str, ref: str, version: object, *, windowed: bool = False) -> str:
        now = time.time()
        for nonce in [n for n, a in self._arms.items() if a[3] < now]:
            del self._arms[nonce]
        nonce = secrets.token_urlsafe(24)
        self._arms[nonce] = (purpose, ref, str(version), now + ARM_SECONDS, windowed)
        return nonce

    def arm_was_windowed(self, token: str | None) -> bool:
        """Whether a window covered the act when this nonce was armed (R9 lapsed needs it)."""
        entry = self._arms.get(token or "")
        return bool(entry) and entry[4]

    def armed(self, purpose: str, ref: str, version: object, token: str | None) -> bool:
        """True once for the nonce `arm` issued for exactly this act, within its 10 s."""
        entry = self._arms.pop(token or "", None)
        return bool(entry) and entry[:3] == (purpose, ref, str(version)) and entry[3] >= time.time()

    # -- cursors: opaque, signed, carrying no scope or count in the clear (§15) ---------------------
    def cursor(self, q: str, offset: int) -> str:
        sig = hmac.new(self._signing, f"cursor|{q}|{offset}".encode(), hashlib.sha256)
        return f"{offset:x}.{sig.hexdigest()[:24]}"

    def offset(self, q: str, cursor: str | None) -> int:
        try:
            off_s, sig = (cursor or "").split(".", 1)
            off = int(off_s, 16)
        except ValueError:
            return 0
        good = hmac.new(self._signing, f"cursor|{q}|{off}".encode(), hashlib.sha256)
        return off if _same(sig, good.hexdigest()[:24]) else 0  # R5: first page

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
                {"current": self.scheme_of(request), "return": here, "csrf": self.form_key}
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
                "around": around,
                "scheme": scheme,
                "printed": time.strftime("%H:%M:%S"),
                "container_name": self.c.home.name,
                **context,
            },
            status_code=status,
        )

    def not_found(self, request: Request, cause: str = "not-found") -> HTMLResponse:
        """R12: one page for not-found, not-yours, tombstoned, quarantined and malformed ids. The
        cause goes to the owner's ledger, never to the page (R6, the tap spec D-T8); the shape of
        that field in `details` is lifeboat.md R6's [GAP→a1p]."""
        self.read("not-found", cause=cause)
        return self.render(
            request,
            "notfound.html",
            # R12: one page for five causes — nothing on it depends on what was asked for.
            {"shell": self.shell(request, current=None, here="/"), "title": S["title.notfound"]},
            status=404,
        )

    # -- the decision, shared by the pending page and the lifeboat-hosted tap ---------------------
    def decide(self, act: dict[str, Any], outcome: str, *, windowed: bool,
               via: str, version: object = None) -> tuple[str, str]:
        """Perform the decision; returns (state, text): the state is what actually happened —
        approved, denied, or invalid for a refusal — so a refusal never reads as a success. A
        promote carries the version that was armed, and an item changed since is refused: the
        act is the one the person saw (tap spec §2.5)."""
        token = self.token()
        at = time.strftime("%H:%M:%S")
        closes = self.presence.record(act, via=via, outcome=outcome, windowed=windowed)
        try:
            if outcome == "denied":
                if act["kind"] == "proposal":
                    self.c.trust.deny(act["subject"], token=token, actor=OWNER)
                    return "denied", t("outcome.denied", at=at, user=OWNER,
                                       destination=act["dest"])
                return "invalid", t("tap.invalid")
            if outcome not in ("approved", "window"):
                return "invalid", t("tap.invalid")
            if act["kind"] == "proposal":
                p = self.c.trust.execute(act["subject"], token=token, actor=OWNER)
                landed = {i.status for i in (self.c.backend.get(x) for x in p["items"]) if i}
                trust = ", ".join(sorted(landed)) or "unverified"
                if closes:
                    return "approved", t("outcome.approved", at=at, user=OWNER,
                                         n=len(p["items"]), destination=act["dest"],
                                         trust=trust, closes=clock(closes))
                return "approved", t("outcome.approved.nowindow", at=at, user=OWNER,
                                     n=len(p["items"]), destination=act["dest"], trust=trust)
            item = self.c.backend.get(act["subject"])
            if item is None or item.status != "unverified":
                raise TrustError("no longer pending")
            if version is not None and str(item.lifecycle.get("version", 1)) != str(version):
                raise TrustError("changed since it was armed")
            self.c.trust.promote(item, token=token, actor=OWNER)
            return "approved", t("act.promoted", at=at, user=OWNER)
        except TrustError as e:
            # Presence was proven and the act was refused: on the chain, and the window that
            # signature opened closes with it — as the CLI does (presence.act_failed).
            self.presence.act_failed(act, e, reason="refused")
            return "invalid", (t("outcome.invalid") if act["kind"] == "proposal"
                               else t("tap.invalid"))
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


def proposal_state(c: Container, pid: str) -> str:
    """A digest of the proposal as stored: what a pending arm is bound to."""
    p = c.backend.get_proposal(pid) or {}
    return hashlib.sha256(json.dumps(p, sort_keys=True, default=str).encode()).hexdigest()[:16]


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
        host = request.headers.get("host")
        key = request.query_params.get("k")
        # Every refusal before the session is proven is the same static page: no shell, no
        # container state, nothing written to the chain. Only the bound hosts are served, so a
        # page elsewhere that rebinds a name to 127.0.0.1 reaches nothing.
        if boat.launch_host is not None and host == boat.launch_host:
            # The launch host does one thing: redeem the key, once, by handing the browser to the
            # session host. It sets no cookie and serves no page.
            if (request.method == "GET" and key is not None and not boat.redeemed
                    and _same(key, boat.key)):
                boat.redeemed = True
                to = f"http://{boat.host}/?{urlencode({'h': boat.hand_off()})}"
                return _harden(RedirectResponse(to, status_code=303), path)
            return _harden(HTMLResponse(_LOCKED, status_code=403), path)
        if host != boat.host:
            return _harden(HTMLResponse(_LOCKED, status_code=403), path)
        handoff = request.query_params.get("h")
        if boat.launch_host is not None and request.method == "GET" and handoff is not None:
            if boat.take_handoff(handoff):
                resp = RedirectResponse("/", status_code=303)
                # Host-only (no Domain): sent to this label host alone, never to 127.0.0.1.
                resp.set_cookie(COOKIE, boat.session, httponly=True, samesite="strict", path="/")
                return _harden(resp, path)
            return _harden(HTMLResponse(_LOCKED, status_code=403), path)
        if boat.launch_host is None and request.method == "GET" and key is not None:
            # The launch key works once: whoever redeems it first holds the session, and a copy
            # read later from a launcher's argv or a terminal opens nothing.
            if not boat.redeemed and _same(key, boat.key):
                boat.redeemed = True
                resp: Response = RedirectResponse(path or "/", status_code=303)
                resp.set_cookie(COOKIE, boat.session, httponly=True, samesite="strict", path="/")
                return _harden(resp, path)
            return _harden(HTMLResponse(_LOCKED, status_code=403), path)
        if not _same(request.cookies.get(COOKIE, ""), boat.session):
            return _harden(HTMLResponse(_LOCKED, status_code=403), path)
        if request.method == "POST":
            # A missing Origin is refused too: every browser sends one on a form POST.
            if request.headers.get("origin") != origin:
                return _harden(HTMLResponse(_REFUSED, status_code=403), path)
        try:
            response = await call_next(request)
            if request.method == "POST" and request.headers.get("hx-request") == "true":
                response = _for_htmx(response)
        except Exception:  # noqa: BLE001 — R12: never a code, path or exception text
            try:
                boat.read("error")  # the card is a view too, when the chain can still take it
            except Exception:  # noqa: BLE001 — a broken container still gets its card
                pass
            response = boat.render(request, "error.html",
                                   {"shell": boat.shell(request, current=None),
                                    "title": S["title.notfound"],
                                    # D-C5: the retry link is a validated return, never the
                                    # raw path (a `//host` path would leave this origin).
                                    "retry": return_target(str(request.url.path))}, status=500)
        return _harden(response, path)

    async def form_of(request: Request) -> dict[str, str] | None:
        form = {k: str(v) for k, v in (await request.form()).items()}
        if not _same(form.get("csrf", ""), boat.form_key):
            return None
        return form

    # -- static: the one stylesheet, the token file, htmx (vendored) -------------------------------
    @app.get("/static/{name}")
    async def static_file(request: Request, name: str):
        files = {
            "tokens.css": ("tokens.css", "text/css; charset=utf-8"),
            "lifeboat.css": ("static/lifeboat.css", "text/css; charset=utf-8"),
            "htmx.min.js": ("static/htmx.min.js", "text/javascript; charset=utf-8"),
            "lifeboat.js": ("static/lifeboat.js", "text/javascript; charset=utf-8"),
        }
        if name == "tap.css":  # the hosted tap's styles, linked so no page needs inline style
            return Response(tap_css(), media_type="text/css; charset=utf-8")
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
            header = S["results.uncounted"] if q else number_free("results.recent")  # R3 empty
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
        """(item, node, None) for an item this page may show, else (None, None, cause). Search's
        predicate (`find.shown`), so the two views never disagree on one item."""
        token = boat.token()
        if not _UNRESERVED.fullmatch(item_id or ""):
            return None, None, "malformed"
        item = boat.c.backend.get(item_id)
        node = boat.c.backend.get_node(item.scope) if item else None
        if not item or not node:
            return None, None, "not-found"
        if item.lifecycle.get("tombstoned"):
            return None, None, "tombstoned"
        if item.status == "quarantined":
            return None, None, "quarantined"
        if not boat.c.trust.covers(token, node) or not shown(boat.c, token, item, node):
            return None, None, "not-yours"
        return item, node, None

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
            "ring": None if node.type == "user" else node.type,
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
                (S["prov.actor"], prov.get("actor")),
                (S["prov.principal"], prov.get("principal")),
                (S["prov.client"], prov.get("client")),
                (S["prov.derived"], derived),
                (S["prov.imported"], prov.get("imported_from")),
                (S["prov.approved"], prov.get("approved_by")),
            ],
            "derived_link": derived_link,
            "promoted": (t("trust.promoted", at=clock(trust.get("promoted_at")),
                           prefix=(trust.get("manifest") or "")[:8])
                         if item.status == "verified" and trust.get("promoted_at") else None),
            "life": [
                (S["life.created"], clock(item.lifecycle.get("created_at")) or S["prov.null"]),
                (S["life.updated"], clock(item.lifecycle.get("updated_at")) or S["prov.null"]),
                (S["life.version"], f"v{item.lifecycle.get('version', 1)}"),
            ],
            "tags": item.tags or [],
            "key": item.key,
            "can_promote": item.status == "unverified",
            "arm": arm,
            "version": item.lifecycle.get("version", 1),
            "csrf": boat.form_key,
            "message": message,
        }

    @app.get("/items/{item_id}", response_class=HTMLResponse)
    async def item_page(request: Request, item_id: str, full: int = 0):
        item, node, cause = item_or_none(item_id)
        if item is None:
            return boat.not_found(request, cause)
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
        item, node, cause = item_or_none(item_id)
        if item is None:
            return boat.not_found(request, cause)
        version = item.lifecycle.get("version", 1)
        if str(form.get("version")) != str(version):
            boat.read("item", subject=item.id, scope=item.scope, items=[item.id])
            return boat.render(request, "item.html", item_context(
                request, item, node, full=False, arm=None,
                message=("invalid", S["act.invalid"])))
        under_window = boat.arm_was_windowed(form.get("arm"))
        if not boat.armed("promote", item.id, version, form.get("arm")):
            # The first press — or a confirm whose 10 s lapsed — arms in place (R9 confirming).
            boat.read("item", subject=item.id, scope=item.scope, items=[item.id])
            act = build_act(boat.c, item.id, token=boat.token())
            covered = act is not None and boat.presence.covers(act)
            ctx = item_context(request, item, node, full=False, message=None,
                               arm=boat.arm("promote", item.id, version, windowed=covered))
            return boat.render(request, "item.html", {**ctx, "refresh": ARM_SECONDS})
        act = build_act(boat.c, item.id, token=boat.token())
        if act is None:
            return boat.not_found(request)
        if boat.presence.covers(act):
            try:
                boat.outcomes[item.id] = boat.decide(act, "window", windowed=False, via="window",
                                                     version=version)
            except Exception:  # noqa: BLE001 — R9 error: decide recorded it; back to ready
                boat.outcomes[item.id] = ("error", S["act.error"])
            return RedirectResponse(f"/items/{item.id}", status_code=303)
        status = boat.presence.window_status()
        if under_window and status and status["state"] == "lapsed":
            # R9 lapsed: the window that covered the first press closed before the second.
            # Nothing changed; the acts return un-armed, and the next press asks for presence.
            boat.outcomes[item.id] = ("lapsed", t("act.lapsed", at=clock(status["at"])))
            return RedirectResponse(f"/items/{item.id}", status_code=303)
        # Step-up required: a one-shot tap, its return bound now (the tap spec D-T9 (a)).
        boat.sweep()

        def perform(outcome: str, windowed: bool) -> str:
            # Runs inside the tap's own request: the container answers before anything is shown.
            state, text = boat.decide(act, outcome, windowed=windowed, via="tap",
                                      version=version)
            boat.outcomes[act["subject"]] = (state, text)
            return text

        tap = Tap(act, container=boat.c.home.name, host=boat.host, decide=perform,
                  stylesheet="/static/tap.css")
        boat.taps[tap.token] = {"tap": tap, "return": return_target(f"/items/{item.id}")}
        return RedirectResponse(f"/tap/{tap.token}", status_code=303)

    @app.get("/items/{item_id}/download")
    async def download(request: Request, item_id: str):
        item, node, cause = item_or_none(item_id)
        token = boat.token()
        data = (boat.c.store.blob_pull(item, token=token, actor=OWNER, principal=token.principal)
                if item is not None and item.kind == "artifact" else None)
        if data is None:
            return boat.not_found(request, cause or "not-found")
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

    def notices() -> list[dict[str, Any]]:
        """Quarantine notices, pinned at the end of the queue (the tap spec §3.1, R3): an item
        that stopped serving because what it was derived from was quarantined. A notice, not an
        act — lifting a quarantine is the CLI's in this lifeboat (§0) — so it has no link."""
        token = boat.token()
        out = []
        for node in boat.c.backend.list_nodes():
            if not boat.c.trust.covers(token, node):
                continue
            for item in boat.c.backend.query([node.id]):
                source = (item.provenance or {}).get("derived_from")
                if item.status == "quarantined" and source and \
                        str((item.trust or {}).get("reason", "")).startswith("derived from"):
                    out.append({"id": item.id, "title": item_title(item), "meta": t(
                        "queue.quarantine.meta", id=f"{source[:8]}…",
                        at=clock((item.trust or {}).get("at"))[:5])})
        return out

    def pending_context(request: Request, pid: str | None, *, arm: dict[str, str] | None,
                        message: tuple[str, str] | None) -> dict[str, Any] | None:
        rows = queue()
        open_id = pid or (rows[0]["id"] if rows else None)
        detail = None
        if open_id:
            act = build_act(boat.c, open_id, token=boat.token())
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
                    "csrf": boat.form_key,
                }
        status = boat.presence.window_status()
        return {
            "shell": boat.shell(request, current="pending", scheme=False),
            "title": S["title.pending"],
            "rows": rows,
            "notices": notices(),
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
        boat.read("pending", proposals=[r["id"] for r in ctx["rows"]],
                  notices=[n["id"] for n in ctx["notices"]])
        return boat.render(request, "pending.html", ctx)

    @app.get("/pending/{pid}", response_class=HTMLResponse)
    async def pending_one(request: Request, pid: str):
        message = boat.outcomes.pop(pid, None)
        ctx = pending_context(request, pid, arm=None, message=message)
        if ctx is None:
            return boat.not_found(request)
        boat.read("pending", subject=pid, proposals=[r["id"] for r in ctx["rows"]],
                  notices=[n["id"] for n in ctx["notices"]])
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
        act = build_act(boat.c, pid, token=boat.token())
        if act is None or act["kind"] != "proposal":
            return boat.not_found(request)
        step = form.get("step", "")
        # The arm binds to the proposal as it stands: any change between the presses (its items,
        # target or status) is a different state, and the confirm re-arms instead of acting.
        state = proposal_state(boat.c, pid)
        if step == "deny":  # one press: deny is the safe direction
            try:
                boat.outcomes[pid] = boat.decide(act, "denied", windowed=False, via="lifeboat")
            except Exception:  # noqa: BLE001 — the tap spec R9 error: decide recorded it
                boat.outcomes[pid] = ("error", S["act.error"])
            return RedirectResponse(f"/pending/{pid}", status_code=303)
        if act.get("blocked"):
            return RedirectResponse(f"/pending/{pid}", status_code=303)
        if step in ("arm", "arm_once"):
            mode = "once" if step == "arm_once" else "window"
            ctx = pending_context(request, pid, arm={"mode": mode,
                                                     "token": boat.arm(mode, pid, state)},
                                  message=None)
            # The armed page shows the whole proposal again: a read on the chain like any view.
            boat.read("pending", subject=pid, proposals=[r["id"] for r in ctx["rows"]],
                      notices=[n["id"] for n in ctx["notices"]])
            return boat.render(request, "pending.html", {**ctx, "refresh": ARM_SECONDS})
        mode = form.get("mode", "window")
        if step == "confirm" and mode in ("once", "window") and boat.armed(
            mode, pid, state, form.get("arm")
        ):
            try:
                boat.outcomes[pid] = boat.decide(act, "approved", windowed=mode == "window",
                                                 via="lifeboat")
            except Exception:  # noqa: BLE001 — the tap spec R9 error: decide recorded it
                boat.outcomes[pid] = ("error", S["act.error"])
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

    @app.exception_handler(StarletteHTTPException)
    async def no_other_shape(request: Request, exc: StarletteHTTPException):
        # R12: a method no route declares (PUT, DELETE, ...) answers with the one not-found page,
        # never the framework's own 405 body. Behind the guard, like every route.
        return boat.not_found(request, "method")

    @app.exception_handler(RequestValidationError)
    async def no_validation_shape(request: Request, exc: RequestValidationError):
        # And a parameter that does not parse (`?full=x`) gets that page too, not a 422 JSON body.
        return boat.not_found(request, "malformed")

    return app


def _for_htmx(resp: Response) -> Response:
    """An act posted through htmx swaps its acts block only when the answer is a page. A redirect
    (an outcome, or the step-up's `/tap/<token>`) is a whole-page navigation instead, and a refusal
    reloads the page, so a swap never lands a fragment the act did not render."""
    if 300 <= resp.status_code < 400 and resp.headers.get("location"):
        return Response(status_code=200, headers={"HX-Redirect": resp.headers["location"]})
    if resp.status_code >= 400:
        resp.headers["HX-Refresh"] = "true"
    return resp


def _harden(resp: Response, path: str) -> Response:
    """lifeboat.md §18 (v1.23): no referrer leaves this origin; no-store, nosniff, framed by no one.

    `same-origin`, never `no-referrer`: under `no-referrer` a browser serialises a form POST's
    Origin as `null` (Fetch, "serializing a request origin"), and the guard refuses any POST whose
    Origin is not this one, so every act would fail in Chromium and Firefox (#130)."""
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    # One CSP for every response (§18): styles and scripts from this origin only. The hosted
    # tap links /static/tap.css rather than carrying the CLI tap page's inline style.
    resp.headers["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'self'; "
        "img-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
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
