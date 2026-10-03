# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The lifeboat, MVP cut: `egzos web` — list, search, item detail and the pending queue
(lifeboat.md §0's scope: no audit view, which stays the CLI's `egzos audit`), served in-process on
loopback only, as the owner's interactive principal.

Presence is the browser session: the URL opened at launch carries a per-launch key (printed only
when no browser could be opened and stdout is a terminal — an agent's shell tool is not one); the
first visit trades it for an HttpOnly, SameSite=Strict cookie, and every request needs that cookie. Every
act (approve, deny) is a POST that also carries the key in the form and must come from
this origin, so another page in the same browser cannot drive it. Unknown ids and missing pages
answer one uniform 404 (silence-not-errors). Everything rendered is escaped: item text is data.

Approving is a human-only act under the step-up rule (`authz/presence.py`): *Approve* redirects to
a one-shot `/tap/<token>` page served here (lifeboat.md R9), where *Sign and approve* then *Confirm
signature* within 10 s performs it — unless an open window covers that ring pair and shape. Every
decision appends `step_up`, and every view is a read that appends `context.fetch` (the header's
pending count included). Owner-only: `egzos web` refuses a client principal.

Standard library only, so the base install stays small. The full lifeboat (FastAPI + Jinja + htmx
against spec/design/lifeboat.md) replaces this in Phase 4.
"""

from __future__ import annotations

import html
import secrets
import threading
import time
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib import resources
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from egzos.authz.presence import (
    Presence,
    Tap,
    build_act,
    is_terminal,
    tap_timeout,
)
from egzos.container import OWNER, Container
from egzos.trust import TrustError

COOKIE = "egzos_k"
DEFAULT_PORT = 7425


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _title(item) -> str:
    c = item.content or {}
    return c.get("auto_title") or c.get("title") or (c.get("body") or "")[:80] or item.id


STYLE = """
body{margin:0;background:var(--egz-canvas);color:var(--egz-ink);font-family:var(--egz-font-ui);
 line-height:var(--egz-lh)}
.frame{max-width:1040px;margin:24px auto;padding:0 16px}
header{display:flex;gap:24px;align-items:baseline;border-bottom:var(--egz-bw) solid var(--egz-rule);
 padding:12px 0;margin-bottom:16px}
header .mark{font-family:var(--egz-font-mono);font-weight:var(--egz-w-semibold);letter-spacing:.04em}
nav a{color:var(--egz-ink);margin-right:16px;text-decoration:none;font-family:var(--egz-font-mono);
 text-transform:uppercase;letter-spacing:var(--egz-tracking-caps);font-size:.8rem}
nav a.on{border-bottom:var(--egz-bw) solid var(--egz-ink)}
form.search{display:flex;gap:8px;margin:0 0 16px}
input[type=text]{flex:1;min-height:44px;padding:0 12px;border:var(--egz-bw) solid var(--egz-rule);
 background:var(--egz-paper);color:var(--egz-ink);font:inherit}
button{min-height:44px;padding:0 16px;border:var(--egz-bw) solid var(--egz-rule);
 background:var(--egz-canvas);color:var(--egz-ink);font:inherit;cursor:pointer}
button.act{background:var(--egz-act);color:var(--egz-act-on);border-color:var(--egz-act)}
button:focus-visible,a:focus-visible,input:focus-visible{outline:var(--egz-focus);outline-offset:3px}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:10px 8px;border-bottom:var(--egz-hair) solid var(--egz-rule-soft);
 vertical-align:top}
th{font-family:var(--egz-font-mono);font-size:.75rem;text-transform:uppercase;
 letter-spacing:var(--egz-tracking-caps)}
.mono{font-family:var(--egz-font-mono);font-feature-settings:var(--egz-tabular);font-size:.85rem}
.badge{font-family:var(--egz-font-mono);font-size:.75rem;padding:2px 6px;
 border:var(--egz-hair) solid var(--egz-ink);text-transform:uppercase}
.badge.verified{background:var(--egz-ink);color:var(--egz-canvas)}
.badge.quarantined{color:var(--egz-alarm);border-color:var(--egz-alarm)}
.card{border:var(--egz-bw) solid var(--egz-rule);box-shadow:var(--egz-off) var(--egz-off) 0
 var(--egz-shadow-ink);padding:16px;margin:0 0 24px;background:var(--egz-canvas)}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
pre{white-space:pre-wrap;background:var(--egz-paper);padding:12px;margin:8px 0}
.flash{border:var(--egz-bw) solid var(--egz-act);padding:12px;margin-bottom:16px}
.flash.err{border-color:var(--egz-alarm)}
.muted{opacity:.7}
"""


class Lifeboat:
    """Request handling, independent of the socket server so tests can drive it directly."""

    def __init__(self, container: Container, key: str | None = None, host: str = "127.0.0.1"):
        self.c = container
        self.key = key or secrets.token_urlsafe(24)
        self.presence = Presence(container)
        self.host = host
        self.since = time.time()
        self.taps: dict[str, dict[str, Any]] = {}  # tap token → {tap, back}
        self.armed: dict[str, float] = {}  # item id → when *Confirm promotion* lapses (R9)

    # -- shared chrome ----------------------------------------------------------------------------
    def page(
        self,
        title: str,
        body: str,
        active: str = "",
        flash: str = "",
        err: bool = False,
        count: int | None = None,
        refresh: int | None = None,
    ) -> str:
        nav = "".join(
            f'<a href="{href}" class="{"on" if name == active else ""}">{name}</a>'
            for name, href in (("items", "/"), ("pending", "/pending"))
        )
        counter = f'<span class="mono muted">{count} pending</span>' if count is not None else ""
        flash_html = f'<div class="flash{" err" if err else ""}">{_e(flash)}</div>' if flash else ""
        return (
            "<!doctype html><html lang=en><head><meta charset=utf-8>"
            '<meta name=viewport content="width=device-width,initial-scale=1">'
            + (f'<meta http-equiv=refresh content="{refresh}">' if refresh else "")
            # §13: three fixed <title>s; a title never carries an item title, id, scope or count.
            + f"<title>{_TAB_TITLES.get(title, 'egzos')}</title>"
            '<link rel=stylesheet href="/static/tokens.css">'
            f"<style>{STYLE}</style></head><body><div class=frame>"
            f"<p class='mono muted shell'>egzos · container {_e(self.c.home.name)} · "
            f"{_e(self.host)}<br>you · {_e(OWNER)} · principal: interactive · present since "
            f"{_e(_since(self.since))}</p>"
            f"<header><span class=mark>egzos</span><nav>{nav}</nav>"
            f"{counter}</header>"
            f"{flash_html}{body}</div></body></html>"
        )

    def _count(self) -> int:
        pend = self.c.trust.pending()
        return len(pend["items"]) + len(pend["proposals"])

    def _read(self, token, view: str, **details) -> int:
        """Every view is a read: one `context.fetch`, the header's pending count included."""
        n = self._count()
        self.c.ledger.append(
            "context.fetch",
            actor=OWNER,
            principal=token.principal,
            subject=details.pop("subject", None),
            scope=details.pop("scope", None),
            client="web",
            view=view,
            pending_count=n,
            layers=details.pop("layers", []),
            withheld=0,
            **details,
        )
        return n

    def approve_button(self, ref: str, back: str, label: str) -> str:
        """*Approve* asks the container; when presence is required it redirects to the tap."""
        return self.form("/approve", {"ref": ref, "back": back}, label, "act")

    # -- the tap, served here (lifeboat.md R9) -------------------------------------------------------
    def _sweep(self) -> None:
        """A tap left undecided past its timeout expires, and says so on the record."""
        for token, entry in list(self.taps.items()):
            tap = entry["tap"]
            if tap.outcome is None and time.time() - tap.opened > tap_timeout():
                self.presence.record(tap.act, via="tap", outcome="expired")
                del self.taps[token]

    def tap_get(self, token: str) -> tuple[int, str]:
        self._sweep()
        entry = self.taps.get(token)
        if not entry or not entry["tap"].live(f"/tap/{token}"):
            return 404, "<p>This request is no longer valid.</p>"
        return entry["tap"].get()

    def tap_post(self, token: str, step: str) -> tuple[int, str]:
        self._sweep()
        entry = self.taps.get(token)
        if not entry or not entry["tap"].live(f"/tap/{token}"):
            return 404, "<p>This request is no longer valid.</p>"
        tap, back = entry["tap"], entry["back"]
        status, body = tap.post(step)
        if tap.outcome is None:
            return status, body
        del self.taps[token]
        return 200, tap.outcome_page(self._decide(tap.act, tap.outcome, tap.windowed), back)

    def _decide(self, act: dict[str, Any], outcome: str, windowed: bool, via: str = "tap") -> str:
        """Record the presence check, then perform the decision. Returns the outcome line."""
        token = self.c.require_token()
        at = time.strftime("%H:%M:%S")
        closes = self.presence.record(act, via=via, outcome=outcome, windowed=windowed)
        try:
            if outcome not in ("approved", "window", "denied"):
                return "Nothing changed."
            if outcome == "denied":
                if act["kind"] == "proposal":
                    self.c.trust.deny(act["subject"], token=token, actor=OWNER)
                    return (
                        f"Denied at {at} by {OWNER}. The items never existed at {act['dest']}. "
                        "Logged. Staged bytes kept 30 days cold."
                    )
                return f"Denied at {at} by {OWNER}. It stays unverified. Logged."
            window = (
                f"Window open until {_clock_of(closes)}." if closes else "No window opened."
            )
            if act["kind"] == "proposal":
                p = self.c.trust.execute(act["subject"], token=token, actor=OWNER)
                landed = {
                    i.status for i in (self.c.backend.get(x) for x in p["items"]) if i
                }
                trust = ", ".join(sorted(landed)) or "unverified"
                return (
                    f"Signed at {at} by {OWNER}. {len(p['items'])} items at {act['dest']}, "
                    f"{trust}. {window}"
                )
            item = self.c.backend.get(act["subject"])
            if item is None or item.status != "unverified":
                return "This request is no longer valid."
            item = self.c.trust.promote(item, token=token, actor=OWNER)
            return f"Promoted at {at} by {OWNER}. Served as verified from now on."  # §13
        except TrustError:
            return (
                "This proposal is no longer valid."
                if act["kind"] == "proposal"
                else "This request is no longer valid."
            )

    def _path(self, node_id: str) -> str:
        node = self.c.backend.get_node(node_id)
        return self.c.nodes.path(node) if node else node_id

    def not_found(self) -> tuple[int, str]:
        return 404, self.page("Not found", "<p>Nothing here.</p>")

    def form(self, action: str, fields: dict[str, str], label: str, cls: str = "") -> str:
        hidden = "".join(
            f'<input type=hidden name="{_e(k)}" value="{_e(v)}">'
            for k, v in {**fields, "csrf": self.key}.items()
        )
        return (
            f'<form method=post action="{_e(action)}" style="display:inline">{hidden}'
            f'<button class="{cls}">{_e(label)}</button></form>'
        )

    # -- views --------------------------------------------------------------------------------------
    def items(self, q: str = "", flash: str = "", err: bool = False) -> tuple[int, str]:
        token = self.c.require_token()
        rows = []
        for node in self.c.backend.list_nodes():
            if not self.c.trust.covers(token, node):
                continue
            for item in self.c.backend.query([node.id], text=q or None):
                rows.append((node, item))
        rows.sort(key=lambda t: t[1].lifecycle.get("updated_at", ""), reverse=True)
        n = self._read(token, "items", query=q or None, items=[i.id for _, i in rows])
        body_rows = "".join(
            f"<tr><td><span class='badge {_e(i.status)}'>{_e(i.status)}</span></td>"
            f"<td class=mono>{_e(i.kind)}</td>"
            f'<td><a href="/items/{_e(i.id)}">{_e(_title(i))}</a>{_meta(i)}</td>'
            f"<td class=mono>{_e(self.c.nodes.path(n))}</td>"
            f"<td class=mono>{_e(_age(i.lifecycle.get('updated_at')))}</td></tr>"
            for n, i in rows
        )
        header = f"Results · {len(rows)}" if q else f"Recent · {len(rows)} items"  # R3
        table = (
            f"<p class=mono>{header}</p>"
            "<table><tr><th>trust</th><th>kind</th><th>item</th><th>scope</th><th>age</th></tr>"
            f"{body_rows}</table>"
            if rows
            else "<p class=muted>"
            + ("No results." if q else "Nothing here yet. Items you can fetch will appear here.")
            + "</p>"
        )
        search = (
            '<h1><label for=q>Search</label></h1><form class=search method=get action="/">'
            f'<input type=text id=q name=q value="{_e(q)}">'
            "<button>Search</button></form>"
        )
        return 200, self.page(
            "Items", search + table, active="items", flash=flash, err=err, count=n
        )

    def item(self, item_id: str, flash: str = "", err: bool = False) -> tuple[int, str]:
        token = self.c.require_token()
        item = self.c.backend.get(item_id)
        node = self.c.backend.get_node(item.scope) if item else None
        if not item or not node or not self.c.trust.covers(token, node):
            return self.not_found()
        n = self._read(
            token, "item", subject=item.id, scope=item.scope, items=[item.id], layers=[node.id]
        )
        content = item.content or {}
        text = content.get("body") or content.get("inline") or ""
        acts = ""
        if item.status == "unverified":
            # R9: a local two-press act — *Promote to verified* arms in place, *Confirm promotion*
            # within 10 s asks the container, which redirects to the tap when presence is needed.
            back = f"/items/{item.id}"
            if self.armed.get(item.id, 0.0) > time.time():
                acts += self.form(
                    "/promote", {"ref": item.id, "back": back, "step": "confirm"},
                    "Confirm promotion", "act",
                )
            else:
                acts += self.form(
                    "/promote", {"ref": item.id, "back": back, "step": "arm"},
                    "Promote to verified", "act",
                )
        body = (
            f"<div class=card><div class=row><span class='badge {_e(item.status)}'>"
            f"{_e(item.status)}</span><span class=mono>{_e(item.kind)}</span>"
            f"<span class=mono>{_e(self.c.nodes.path(node))}</span></div>"
            f"<h1>{_e(_title(item))}</h1>"
            + (f"<pre>{_e(text)}</pre>" if text else "")
            + "</div><table>"
            + "".join(
                f"<tr><th>{_e(k)}</th><td class=mono>{_e(v)}</td></tr>"
                for k, v in (
                    ("id", item.id),
                    ("key", item.key),
                    ("tags", ", ".join(item.tags)),
                    ("provenance", item.provenance),
                    ("trust", item.trust),
                    ("lifecycle", item.lifecycle),
                )
            )
            + f"</table><div class=row style='margin-top:16px'>{acts}</div>"  # acts last (§3.1)
        )
        armed = self.armed.get(item.id, 0.0) > time.time()
        return 200, self.page(
            "item", body, flash=flash, err=err, count=n, refresh=10 if armed else None
        )

    def pending(self, flash: str = "", err: bool = False) -> tuple[int, str]:
        token = self.c.require_token()
        pend = self.c.trust.pending()
        n = self._read(
            token,
            "pending",
            items=[i.id for i in pend["items"]],
            proposals=[p["id"] for p in pend["proposals"]],
        )
        props = "".join(
            "<div class=card>"
            f"<p><strong>Move {len(p['items'])} item(s)</strong> "
            f"<span class=mono>{_e(p['from_path'])} → {_e(p['to_path'])}</span></p>"
            "<p>This widens who can read it to: "
            + ", ".join(
                f"<span class=mono>{_e(a['client'])} ({_e(a['role'])})</span>"
                for a in p["audience_delta"]
            )
            + f"</p><p class=muted>{_e(p['blast_radius'])} container(s) under the target inherit it."
            f" Reason: {_e(p['reason'])}</p><div class=row>"
            + (
                "<p class='flash err'>Contains a quarantined item. It cannot move.</p>"
                if any(
                    (i := self.c.backend.get(x)) and i.status == "quarantined" for x in p["items"]
                )
                else self.approve_button(p["id"], "/pending", "Approve this move")
            )
            + self.form("/deny", {"proposal": p["id"], "back": "/pending"}, "Deny")
            + "</div></div>"
            for p in pend["proposals"]
        )
        items = "".join(
            f'<tr><td class=mono>{_e(i.kind)}</td><td><a href="/items/{_e(i.id)}">'
            f"{_e(_title(i))}</a>{_meta(i)}</td><td class=mono>{_e(self._path(i.scope))}</td>"
            f"<td class=mono>{_e((i.provenance or {}).get('client'))}</td><td>"
            + self.approve_button(i.id, "/pending", "Approve")
            + "</td></tr>"
            for i in pend["items"]
        )
        waiting = len(pend["items"]) + len(pend["proposals"])
        body = (
            "<h1>Pending</h1>"
            + (
                f"<p class=mono>{waiting} waiting for you</p>"
                if waiting
                else "<p class=muted>Nothing is waiting for you.</p>"
            )
            + "<h2>Moves waiting for your yes</h2>"
            + (props or "")
            + "<h2>Captured items, unverified</h2>"
            + (
                "<table><tr><th>kind</th><th>item</th><th>scope</th><th>from</th><th></th></tr>"
                f"{items}</table>"
                if items
                else ""
            )
        )
        return 200, self.page(
            "Pending", body, active="pending", flash=flash, err=err, count=n
        )

    # -- acts ---------------------------------------------------------------------------------------
    def act(self, path: str, form: dict[str, str]) -> tuple[int, str, str]:
        """Returns (status, body, redirect). Redirect wins when set."""
        self.c.require_token()  # the owner session is required for every act
        back = form.get("back", "/pending")
        if not back.startswith("/") or back.startswith("//"):
            back = "/pending"
        try:
            if path == "/promote":
                ref = form.get("ref", "")
                act = build_act(self.c, ref)
                if not act or act["kind"] != "item":
                    return (*self.not_found(), "")
                if form.get("step") != "confirm" or self.armed.pop(ref, 0.0) <= time.time():
                    self.armed[ref] = time.time() + 10
                    return 200, "", back
                path = "/approve"  # confirmed in place: now the container decides on presence
            if path == "/approve":
                ref = form.get("ref", "")
                act = build_act(self.c, ref)
                if not act:
                    return (*self.not_found(), "")
                if act.get("blocked"):
                    return 200, "", f"{back}?{urlencode({'err': act['blocked']})}"
                if self.presence.covers(act):
                    msg = self._decide(act, "window", False, via="window")
                    return 200, "", f"{back}?{urlencode({'ok': msg})}"
                self._sweep()
                tap = Tap(act, container=self.c.home.name, host=self.host)
                self.taps[tap.token] = {"tap": tap, "back": back}
                return 200, "", f"/tap/{tap.token}"
            elif path == "/deny":
                act = build_act(self.c, form.get("proposal", ""))
                if not act or act["kind"] != "proposal":
                    return (*self.not_found(), "")
                msg = self._decide(act, "denied", False, via="lifeboat")
            else:
                return (*self.not_found(), "")
        except TrustError as e:
            return 200, "", f"{back}?{urlencode({'err': str(e)})}"
        return 200, "", f"{back}?{urlencode({'ok': msg})}"

    # -- routing ------------------------------------------------------------------------------------
    def get(self, path: str, query: dict[str, str]) -> tuple[int, str]:
        flash, err = (query.get("err"), True) if query.get("err") else (query.get("ok", ""), False)
        if path == "/":
            status, body = self.items(query.get("q", ""), flash, err)
        elif path == "/pending":
            status, body = self.pending(flash, err)
        elif path.startswith("/items/"):
            status, body = self.item(path[len("/items/") :], flash, err)
        else:
            return self.not_found()
        return status, body


_TAB_TITLES = {"Items": "egzos · search", "item": "egzos · item"}


def _age(stamp: str | None) -> str:
    """§2.4's age column: how long ago, in the largest whole unit."""
    try:
        then = time.mktime(time.strptime(stamp or "", "%Y-%m-%dT%H:%M:%SZ")) - time.timezone
    except ValueError:
        return ""
    secs = max(0, int(time.time() - then))
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= size:
            return f"{secs // size}{unit}"
    return f"{secs}s"


def _meta(item) -> str:
    """§2.4's second line: `agent:<actor> · v<version>`, then the tags."""
    who = (item.provenance or {}).get("client") or "cli"
    version = (item.lifecycle or {}).get("version", 1)
    tags = " ".join(f"#{t}" for t in (item.tags or []))
    return (
        f"<div class='mono muted'>agent:{_e(who)} · v{_e(version)}"
        + (f" · {_e(tags)}" if tags else "")
        + "</div>"
    )


def _since(ts: float) -> str:
    t = time.localtime(ts)
    off = time.strftime("%z", t) or "+0000"
    sign = "−" if off[0] == "-" else "+"
    return f"{time.strftime('%H:%M', t)} (UTC{sign}{off[1:3]}:{off[3:5]})"


def _clock_of(iso: str | None) -> str:
    if not iso:
        return ""
    from datetime import UTC, datetime

    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).astimezone().strftime(
        "%H:%M:%S"
    )


def _tokens_css() -> bytes:
    return resources.files("egzos.web").joinpath("tokens.css").read_bytes()


def make_handler(boat: Lifeboat, origin: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "egzos"
        sys_version = ""

        def log_message(self, *args):  # the audit chain is the record, not stderr
            return

        def _send(
            self,
            status: int,
            body: str | bytes,
            ctype: str = "text/html; charset=utf-8",
            headers: dict[str, str] | None = None,
        ) -> None:
            data = body.encode() if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'self' 'unsafe-inline'; form-action 'self'; "
                "frame-ancestors 'none'; base-uri 'none'",
            )
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _redirect(self, to: str, cookie: str | None = None) -> None:
            headers = {"Location": to}
            if cookie:
                headers["Set-Cookie"] = cookie
            self._send(303, "", headers=headers)

        def _authed(self) -> bool:
            jar = SimpleCookie(self.headers.get("Cookie", ""))
            got = jar.get(COOKIE)
            return bool(got) and secrets.compare_digest(got.value, boat.key)

        def do_GET(self):  # noqa: N802 (http.server's name)
            url = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            if "k" in query:
                if secrets.compare_digest(query["k"], boat.key):
                    cookie = f"{COOKIE}={boat.key}; HttpOnly; SameSite=Strict; Path=/"
                    return self._redirect(url.path or "/", cookie)
                return self._send(*boat.not_found())
            if not self._authed():
                return self._send(
                    403,
                    boat.page(
                        "Locked", "<p>Open the link `egzos web` printed in your terminal.</p>"
                    ),
                )
            if url.path == "/static/tokens.css":
                return self._send(200, _tokens_css(), "text/css; charset=utf-8")
            if url.path.startswith("/tap/"):
                return self._send(*boat.tap_get(url.path[len("/tap/") :]))
            return self._send(*boat.get(url.path, query))

        def do_POST(self):  # noqa: N802
            # A missing Origin is refused too: every browser sends one on a form POST.
            if not self._authed() or self.headers.get("Origin") != origin:
                return self._send(403, boat.page("Locked", "<p>Refused.</p>"))
            length = min(int(self.headers.get("Content-Length") or 0), 64 * 1024)
            form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
            path = urlparse(self.path).path
            if path.startswith("/tap/"):
                # The tap's own form carries no csrf field: its unguessable one-shot path, the
                # cookie and the Origin are the guard (the page is the same whichever host serves it).
                return self._send(*boat.tap_post(path[len("/tap/") :], form.get("step", "")))
            if not secrets.compare_digest(form.get("csrf", ""), boat.key):
                return self._send(403, boat.page("Locked", "<p>Refused.</p>"))
            status, body, redirect = boat.act(urlparse(self.path).path, form)
            if redirect:
                return self._redirect(redirect)
            return self._send(status, body)

    return Handler


def _launch(url: str, open_browser: bool, opener=None, terminal=None) -> bool:
    """Open the browser on the keyed URL. The key is printed only when no browser was opened AND
    stdout is a terminal: an agent's shell tool is not a terminal, so it never reads the key.
    Runs on its own thread — some launchers wait for the browser to exit."""
    if open_browser and (opener or webbrowser.open)(url):
        print("Opened in your browser.", flush=True)
        return True
    if (terminal if terminal is not None else is_terminal()):
        print(f"Open this in your browser (it carries this session's key):\n  {url}", flush=True)
    else:
        print(
            "No browser was opened and this is not a terminal, so the session key is not printed. "
            "Run `egzos web` from a terminal on this machine.",
            flush=True,
        )
    return False


def serve_web(container: Container, port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    token = container.require_token()
    if token.principal != "interactive":
        raise PermissionError("the lifeboat is the owner's; a client principal cannot open it")
    host = "127.0.0.1"
    boat = Lifeboat(container, host=f"{host}:{port}")
    httpd = HTTPServer((host, port), make_handler(boat, f"http://{host}:{port}"))
    url = f"http://{host}:{port}/?k={boat.key}"
    print(f"egzos web on http://{host}:{port} — loopback only. Ctrl-C to stop.", flush=True)
    threading.Thread(target=_launch, args=(url, open_browser), daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
