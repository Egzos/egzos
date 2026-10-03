# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The step-up tap, MVP cut (spec/design/step-up-tap-and-pending-approval.md §2, lifeboat baseline).

A human-only act does not happen on a terminal's or a form's say-so. The container serves a
one-shot page at `/tap/<token>` (an opaque single-use token, no parameters, no-referrer, no-store)
with §2.2's content — the container and viewer lines, what moves, who will see it and the
consequence, the presence block — and waits for a decision: *Sign and approve* then *Confirm
signature* within 10 s, *Approve without a window* then the same confirm, or *Deny* (one press).

The CLI (`trust approve` / `trust deny`) opens a loopback server just for the page. `Tap` is
host-agnostic (`get` / `post` / `live`), so the lifeboat can serve the same page when it lands.

Every presence check is one `step_up` entry, whatever its outcome (`approved`, `denied`, `expired`,
`unavailable`, or `window` when an open window covered it), with the source → destination ring
pair. With `step_up.window_seconds` set, a signature opens a window for that ring pair BOUNDED TO
THE MANIFEST'S SHAPE (up to K items of the signed kinds), read back from the chain; `egzos trust
close-window` appends the entry that ends every window. The policy defaults to the contract's 300 s
(container.md §8); `EGZOS_STEP_UP_WINDOW_SECONDS=0` makes every act tap, and #117 holds the default.

The CLI's page opens in the browser; its URL is printed only when no browser could be opened AND
stdout is a terminal: an agent's shell tool is not a terminal, so it never receives a URL to press.

The page is a plain `<form method=post>` two-step on a loopback `http.server`: the tap spec's
baseline, which "works without htmx" (§18); the htmx enhancement is optional there.

Residuals, named: a process running as the user that drives a browser, fakes a terminal, or appends
to the chain directly can do what the user can — a shell running as the user is the user. The URL
travels in the browser launcher's argv, readable by other local users on a shared host, as the
client secret does in `claude mcp add`'s argv under `connect --apply`. The armed confirm reverts
on 10 s only: §2.3 also names Escape and focus leaving the control, which a page with no script
cannot observe — design-gap #119 holds the choice. Audience
chips carry no contractor / external flag: tokens record no principal class yet. OS-backed
presence (WebAuthn / platform authenticator) is the stronger tier the spec names for later.
"""

from __future__ import annotations

import html
import os
import secrets
import sys
import threading
import time
import webbrowser
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs

from egzos._term import safe
from egzos._types import CONTAINER_CONFIG_DEFAULTS
from egzos.container import OWNER, Container

# The one default, from the typed contract (container.md §8, 300 s for a window bounded to the
# manifest's shape): no second constant beside it. `EGZOS_STEP_UP_WINDOW_SECONDS=0` opts out.
DEFAULT_WINDOW_SECONDS = CONTAINER_CONFIG_DEFAULTS["step_up_window_seconds"]
ARM_SECONDS = 10
CHIPS = 6
ROWS = 12  # §2.2 item 5: 12 rows, then `+ N more`
REASON_MAX = 480  # §2.2 item 4: then `…` and *Show full reason*


def window_seconds() -> int:
    """`step_up.window_seconds` (container.md §8). `0` is a value: no window, every act taps."""
    raw = os.environ.get("EGZOS_STEP_UP_WINDOW_SECONDS")
    if raw is None or raw == "":
        return DEFAULT_WINDOW_SECONDS
    seconds = max(0, int(raw))
    # The policy is in whole minutes (§13 `presence.text` has only the N-minute form): round up.
    return -(-seconds // 60) * 60


def tap_timeout() -> float:
    return float(os.environ.get("EGZOS_TAP_TIMEOUT_SECONDS") or 180)


def is_terminal() -> bool:
    """Whether a printed URL would reach a person at a terminal rather than a program's pipe."""
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def _now() -> float:
    return time.time()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clock(ts: float) -> str:
    return datetime.fromtimestamp(ts).astimezone().strftime("%H:%M:%S")


def _local(iso: str | None) -> str:
    """A stored UTC stamp as the page's other clocks read: local `HH:MM:SS`."""
    try:
        return _clock(datetime.strptime(iso or "", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp())
    except ValueError:
        return ""


def _since(ts: float) -> str:
    """`HH:MM (UTC−07:00)` — local time with its zone, as `shell.viewer` renders it."""
    t = datetime.fromtimestamp(ts).astimezone()
    off = t.strftime("%z") or "+0000"
    sign = "−" if off[0] == "-" else "+"
    return f"{t.strftime('%H:%M')} (UTC{sign}{off[1:3]}:{off[3:5]})"


def pair_of(act: dict[str, Any]) -> tuple[str, str]:
    """The source → destination RING pair (types, not paths) a window is keyed on."""
    pair = act.get("pair") or (act["from"], act["to"])
    return (pair[0], pair[1])


def shape_of(act: dict[str, Any]) -> dict[str, Any]:
    """The manifest's shape a window is bounded to: how many items, of which kinds."""
    items = act.get("items", [])
    return {"max_items": len(items), "kinds": sorted({str(r.get("kind")) for r in items})}


def _fits(shape: dict[str, Any], bound: dict[str, Any] | None) -> bool:
    if not bound:
        return False  # a window with no recorded shape covers nothing
    return shape["max_items"] <= bound.get("max_items", 0) and set(shape["kinds"]) <= set(
        bound.get("kinds", [])
    )


# --- what a decision is about ---------------------------------------------------------------------
def short_id(value: str) -> str:
    """The tap spec §5 id: first 8 characters, ` … `, last 4; the full id goes in `title`."""
    return f"{value[:8]} … {value[-4:]}" if len(value) > 12 else value


def build_act(c: Container, ref: str) -> dict[str, Any] | None:
    """The tap's content for an open proposal or an unverified item; None if there is nothing to
    decide. Everything the page shows comes from here, for the CLI and the lifeboat alike."""
    prop = c.backend.get_proposal(ref)
    if prop and prop.get("status") == "open":
        frm, to = c.backend.get_node(prop["from"]), c.backend.get_node(prop["to"])
        items = [i for i in (c.backend.get(x) for x in prop["items"]) if i]
        by = prop.get("proposed_by", {})
        return {
            "kind": "proposal",
            "subject": prop["id"],
            "ref": "PROPOSAL",
            "filed": _local(prop.get("created_at")),
            "title": f"Move {len(items)} items outward: {prop['from_path']} → {prop['to_path']}",
            "requester": f"agent:{by['client']}" if by.get("principal") == "client" else "you",
            "reason": prop.get("reason"),
            "items": [
                {"kind": i.kind, "title": i.content.get("auto_title", i.id),
                 "quarantined": i.status == "quarantined",
                 "now": i.status,
                 "reset": by.get("principal") != "interactive" and i.status == "verified",
                 "after": (
                     "unverified"
                     if by.get("principal") != "interactive" and i.status == "verified"
                     else i.status
                 ),
                 "trust": (
                     "verified → unverified · agent-run move resets"
                     if by.get("principal") != "interactive" and i.status == "verified"
                     else f"{i.status} → {i.status}"
                 )}
                for i in items
            ],
            "audience": prop.get("audience", []),
            "dest": prop["to_path"],
            # §4 R6: the sentence follows the destination's ring — an exo room's audience is
            # its named external parties, not a subtree.
            "consequence": (
                TAP_COPY["consequence.exo"].format(name=to.name)
                if to and to.type == "exo"
                else TAP_COPY["consequence"].format(destination=prop["to_path"])
            ),
            "from": prop["from_path"],
            "to": prop["to_path"],
            "pair": (frm.type if frm else "?", to.type if to else "?"),
            "blocked": (
                "Contains a quarantined item. It cannot move." if any(i.status == "quarantined" for i in items) else None
            ),
        }
    item = c.backend.get(ref)
    node = c.backend.get_node(item.scope) if item else None
    if item and node and item.status == "unverified":
        path = c.nodes.path(node)
        client = (item.provenance or {}).get("client")
        return {
            "kind": "item",
            "subject": item.id,
            "ref": "ITEM",
            "filed": None,
            # Interim, named on design-gap #122: the tap spec's §2.2 item 3 titles a proposal
            # (a ring pair) and has no title for approve.pending.
            "title": f"Mark verified: “{item.content.get('auto_title', item.id)}” at {path}",
            "requester": f"agent:{client}" if client and client != "cli" else "you",
            "reason": None,
            "items": [{"kind": item.kind, "title": item.content.get("auto_title", item.id),
                       "trust": "unverified → verified", "now": "unverified",
                       "after": "verified", "reset": False, "quarantined": False}],
            "audience": c.trust.audience(node),
            "dest": path,
            "consequence": None,
            "from": path,
            "to": path,
            "pair": (node.type, node.type),
        }
    return None


class Presence:
    def __init__(self, container: Container):
        self.c = container

    # -- windows, read back from the chain ---------------------------------------------------------
    def _recent_step_ups(self, seconds: int) -> list[dict[str, Any]]:
        """`step_up` entries newer than `seconds` ago, newest first. Pages back through the tail
        until it is older than that, so a busy chain cannot hide a window or a close."""
        since = _iso(_now() - seconds - 1)
        n = 256
        while True:
            rows = self.c.ledger.tail(n)
            if len(rows) < n or not rows or rows[0]["ts"] < since:
                break
            n *= 4
        return [r for r in reversed(rows) if r["ts"] >= since and r["event"] == "step_up"]

    def window_open(self, pair: tuple[str, str], shape: dict[str, Any] | None = None) -> bool:
        """Whether an open window covers this ring pair — and, given a shape, this many items of
        these kinds. A window only ever covers what fits the shape that was signed."""
        seconds = window_seconds()
        if seconds == 0:
            return False
        now = _iso(_now())
        for e in self._recent_step_ups(seconds):
            d = e.get("details") or {}
            if d.get("outcome") == "closed":
                return False  # Close window now ends every window opened before it
            if (
                d.get("outcome") == "approved"
                and d.get("pair") == list(pair)
                and (d.get("window_closes") or "") > now
                and (shape is None or _fits(shape, d.get("shape")))
            ):
                return True
        return False

    def covers(self, act: dict[str, Any]) -> bool:
        # A manifest holding a quarantined item cannot be approved (R5): no window stands in for it.
        if act.get("blocked"):
            return False
        return self.window_open(pair_of(act), shape_of(act))

    def act_failed(self, act: dict[str, Any], error: BaseException, *,
                   reason: str = "act failed", actor: str = OWNER) -> None:
        """The presence was proven and the act did not land: it failed and rolled back whole, or
        the engine refused it. The chain says so, and the window that signature opened closes
        with it, so neither a failure nor a refusal leaves one open."""
        self.c.ledger.append(
            "step_up", actor=actor, principal="interactive", subject=act.get("subject"),
            via="tap", outcome="closed", reason=reason, error=type(error).__name__,
        )

    def close_windows(self, *, actor: str = OWNER) -> None:
        self.c.ledger.append(
            "step_up", actor=actor, principal="interactive", via="close", outcome="closed"
        )

    def record(
        self,
        act: dict[str, Any],
        *,
        via: str,
        outcome: str,
        windowed: bool = False,
        actor: str = OWNER,
    ) -> str | None:
        """One `step_up` per presence check, whatever the outcome. Returns the window's close."""
        closes = None
        seconds = window_seconds()
        if outcome == "approved" and windowed and seconds:
            closes = _iso(_now() + seconds)
        self.c.ledger.append(
            "step_up",
            actor=actor,
            principal="interactive",
            subject=act.get("subject"),
            via=via,
            outcome=outcome,
            pair=list(pair_of(act)),
            shape=shape_of(act) if closes else None,
            window_closes=closes,
        )
        return closes

    # -- the CLI's tap: a loopback server for one page ----------------------------------------------
    def require(self, act: dict[str, Any], *, timeout: float | None = None, opener=None,
                decide=None) -> str:
        """Ask for presence. Returns "window", "approved", "denied", "expired" or "unavailable".

        `decide(outcome, windowed, closes) -> str` performs the decision while the page waits and returns
        the outcome line the page then shows — the container's answer, never a prediction. The
        `step_up` entry is appended first, so the chain reads presence, then the act."""
        if timeout is None:
            timeout = tap_timeout()
        if self.covers(act):
            self.record(act, via="window", outcome="window")
            return "window"
        httpd = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
        host = f"127.0.0.1:{httpd.server_address[1]}"
        def decided(outcome: str, windowed: bool) -> str:
            closes = self.record(act, via="tap", outcome=outcome, windowed=windowed)
            try:
                if decide is not None:
                    return decide(outcome, windowed, closes)
                return outcome_text(act, outcome, closes=closes)
            except Exception as e:
                self.act_failed(act, e)
                print(safe(f"That didn't go through. Nothing changed. ({e})"),
                      file=sys.stderr, flush=True)
                raise

        tap = Tap(act, container=self.c.home.name, host=host, decide=decided)
        httpd.RequestHandlerClass = tap.handler()
        url = f"http://{host}/tap/{tap.token}"
        # The opener runs on its own thread: some browsers' launchers wait for the browser, and the
        # page cannot be served until this thread starts answering requests below.
        result: list[bool] = []
        launcher = threading.Thread(
            target=lambda: result.append(bool((opener or webbrowser.open)(url))), daemon=True
        )
        launcher.start()
        launcher.join(2.0)
        opened = result[0] if result else True
        if opened:
            print("A presence check opened in your browser. Decide there.", flush=True)
        elif is_terminal():
            print(f"Open this to decide (it works once):\n  {url}", flush=True)
        else:
            httpd.server_close()
            print(
                "No browser could be opened and this is not a terminal, so the presence check "
                "cannot be shown. Run the command from a terminal on this machine.",
                flush=True,
            )
            self.record(act, via="tap", outcome="unavailable")
            return "unavailable"
        httpd.timeout = 1.0
        deadline = _now() + timeout
        while tap.outcome is None and _now() < deadline:
            httpd.handle_request()
        httpd.server_close()
        if tap.outcome is None:
            self.record(act, via="tap", outcome="expired")
        return tap.outcome or "expired"


# --- the page --------------------------------------------------------------------------------------
# The page consumes the design tokens (spec/design/tokens.css, vendored at egzos/web/tokens.css) as
# CSS variables, inlined because the page's CSP loads nothing; the scheme follows tokens.css's own
# rule (data-scheme, else prefers-color-scheme). No literal colour lives here.
TAP_STYLE = """
body{margin:0;background:var(--egz-canvas);color:var(--egz-ink);font-family:var(--egz-font-ui);
 line-height:var(--egz-lh)}
main{max-width:720px;margin:var(--egz-sp-6) auto;padding:0 var(--egz-sp-4)}
h1{font-size:var(--egz-fs-6);font-weight:var(--egz-w-semibold)}
h2{font-size:var(--egz-fs-4);font-weight:var(--egz-w-semibold)}
.stamp{font-family:var(--egz-font-mono);font-size:var(--egz-fs-1);text-transform:uppercase;
 padding:0 var(--egz-sp-1);
 border:var(--egz-hair) solid var(--egz-ink)}
.stamp--verified{background:var(--egz-ink);color:var(--egz-canvas)}
.stamp--quarantined{color:var(--egz-alarm);border-color:var(--egz-alarm)}
.ink3{color:var(--egz-ink-3)}
.chips{list-style:none;padding:0;display:flex;flex-wrap:wrap;gap:var(--egz-sp-2)}
.attr{font-family:var(--egz-font-mono);font-size:var(--egz-fs-2)}
summary{cursor:pointer;font-family:var(--egz-font-mono);font-size:var(--egz-fs-2);min-height:44px;
 padding:var(--egz-sp-3) 0;box-sizing:border-box}
.ref,.shell{font-family:var(--egz-font-mono);text-transform:uppercase;
 letter-spacing:var(--egz-tracking-caps);font-size:var(--egz-fs-1);
 font-feature-settings:var(--egz-tabular)}
.ref code{font:inherit}
.shell{text-transform:none;letter-spacing:0;border-bottom:var(--egz-hair) solid var(--egz-rule-soft);
 margin:0;padding:var(--egz-sp-1) 0}
.box,.note,.alarm,button{box-shadow:var(--egz-off) var(--egz-off) 0 var(--egz-shadow-ink)}
button,summary,.box,.note,.alarm,.chip,.stamp,table{border-radius:var(--egz-radius)}
button{-webkit-appearance:none;appearance:none}
.box{border:var(--egz-bw) solid var(--egz-rule);padding:var(--egz-sp-4);
 margin:var(--egz-sp-4) var(--egz-off) calc(var(--egz-sp-4) + var(--egz-off)) 0}
.chip{display:inline-block;border:var(--egz-hair) solid var(--egz-rule);
 padding:var(--egz-sp-1) var(--egz-sp-2);margin:0 var(--egz-sp-2) var(--egz-sp-2) 0;
 font-family:var(--egz-font-mono);font-size:var(--egz-fs-2)}
table{width:100%;border-collapse:collapse}
th{text-align:left;padding:var(--egz-sp-2) var(--egz-sp-1)}
td{padding:var(--egz-sp-2) var(--egz-sp-1);border-bottom:var(--egz-hair) solid var(--egz-rule-soft)}
button{min-height:44px;padding:0 var(--egz-sp-4);border:var(--egz-bw) solid var(--egz-rule);
 background:var(--egz-canvas);color:var(--egz-ink);font:inherit;cursor:pointer;
 margin:0 var(--egz-sp-2) var(--egz-sp-2) 0}
button.act{background:var(--egz-act);color:var(--egz-act-on);border-color:var(--egz-act)}
button.ghost{border-color:transparent;text-decoration:underline;box-shadow:none}
button:active{transform:translate(var(--egz-off),var(--egz-off));box-shadow:none}
button:focus-visible,a:focus-visible{outline:var(--egz-focus);outline-offset:3px}  /* tokens.css --egz-focus */
.note{border:var(--egz-bw) solid var(--egz-act);padding:var(--egz-sp-3);
 margin:0 var(--egz-off) var(--egz-sp-4) 0}
.alarm{border:var(--egz-bw) solid var(--egz-alarm);color:var(--egz-alarm);padding:var(--egz-sp-3);
 margin:0 var(--egz-off) var(--egz-sp-4) 0}
.qrow td{color:var(--egz-alarm)}
.terms{font-family:var(--egz-font-mono);font-feature-settings:var(--egz-tabular);
 font-size:var(--egz-fs-2)}
"""


def _tokens_css() -> str:
    from importlib import resources

    return resources.files("egzos.web").joinpath("tokens.css").read_text(encoding="utf-8")


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def presence_text(act: dict[str, Any], seconds: int) -> str:
    """§13 `presence.text` / `presence.zero`, verbatim."""
    if not seconds:
        return "Signing proves you are here. No window opens."
    frm, to = act["from"], act["to"]
    shape = shape_of(act)
    return (
        f"Approving is a human-only act. Signing proves you are here and opens a "
        f"{seconds // 60}-minute window "
        f"for {frm} → {to}, bounded to this shape: up to {shape['max_items']} items of kinds "
        f"{', '.join(shape['kinds'])}. Moves inside the window pass without asking and are logged."
    )


TAP_COPY = {
    "outcome.approved": "Signed at {at} by {user}. {n} items at {destination}, {trust}. "
    "Window open until {closes}.",
    "outcome.approved.nowindow": "Signed at {at} by {user}. {n} items at {destination}, {trust}. "
    "No window opened.",
    "outcome.denied": "Denied at {at} by {user}. The items never existed at {destination}. "
    "Logged. Staged bytes kept 30 days cold.",
    "outcome.invalid": "This proposal is no longer valid.",
    "act.promoted": "Promoted at {at} by {user}. Served as verified from now on.",
    "tap.invalid": "This request is no longer valid.",
    "tap.empty": "Nothing is waiting for you.",
    "act.confirm.sr": "Press again to confirm.",
    "act.error": "That didn't go through. Nothing changed. Try again.",
    "consequence": "Consequence. Everything under {destination} inherits this — every team, "
    "project and thread, now and in future.",
    "consequence.exo": "Consequence. Everything in the exo room {name} sees this — every named "
    "external party, now and in future.",
}


def outcome_text(act: dict[str, Any], outcome: str, *, closes: str | None,
                 landed: list[str] | None = None) -> str:
    """The canonical outcome line for a decision the container has answered."""
    at = _clock(_now())
    if outcome == "denied":
        if act.get("kind") == "proposal":
            return TAP_COPY["outcome.denied"].format(at=at, user=OWNER, destination=act["dest"])
        return TAP_COPY["tap.invalid"]
    if act.get("kind") != "proposal":
        # lifeboat.md §13's string for this act; the tap spec's §13 has none (#122).
        return TAP_COPY["act.promoted"].format(at=at, user=OWNER)
    trust = ", ".join(sorted(set(landed or [r.get("after", "unverified")
                                               for r in act.get("items", [])])))
    key = "outcome.approved" if closes else "outcome.approved.nowindow"
    return TAP_COPY[key].format(at=at, user=OWNER, n=len(act.get("items", [])),
                                destination=act["dest"], trust=trust,
                                closes=_local(closes) if closes else "")


def _chip(a: dict[str, Any]) -> str:
    who = a.get("owner") if a.get("principal") == "interactive" else f"agent:{a.get('client')}"
    return f"{who} · {a.get('role')}"


class Tap:
    """One page, one decision. The token is single-use: after a decision every request is refused."""

    def __init__(self, act: dict[str, Any], *, container: str = "egzos", host: str = "",
                 decide=None):
        self.act = act
        # The host's callback: performs the decision and returns the container's outcome line, so
        # the page never shows an outcome before the container has answered (lifeboat.md §15).
        self.decide = decide
        self.token = secrets.token_urlsafe(32)
        self.container = container
        self.host = host
        self.opened = _now()
        self.outcome: str | None = None
        self.windowed = True
        self.armed_until = 0.0
        self.armed_mode = "window"

    @property
    def gate(self) -> bool:
        """A parked proposal (gate.confirm: approve or deny), not an item promotion."""
        return self.act.get("kind") == "proposal"

    def page(self, armed: bool, note: str = "", error: str = "") -> str:
        a = self.act
        e = _e
        seconds = window_seconds()
        def stamp(word: str) -> str:
            return f"<span class='stamp stamp--{e(word)}'>{e(word)}</span>"

        def row(r: dict[str, Any]) -> str:
            if r.get("quarantined"):  # R5: the row carries its stamp and reads red
                return (f"<tr class=qrow><td>{e(r.get('kind'))}</td><td>{e(r.get('title'))}</td>"
                        f"<td>{stamp('quarantined')}</td><td>{stamp('quarantined')}</td></tr>")
            now = r.get("now") or ""
            after = r.get("after") or ""
            note = " <span class=ink3>agent-run move resets</span>" if r.get("reset") else ""
            return (f"<tr><td>{e(r.get('kind'))}</td><td>{e(r.get('title'))}</td>"
                    f"<td>{stamp(now)}</td><td>{stamp(after)}{note}</td></tr>")

        head = ("<thead><tr><th scope=col>kind</th><th scope=col>item</th>"
                "<th scope=col>trust now</th><th scope=col>after move</th></tr></thead>")
        manifest = [row(r) for r in a.get("items", [])]
        rows = f"<table>{head}<tbody>{''.join(manifest[:ROWS])}</tbody></table>"
        if len(manifest) > ROWS:  # expands in place, no script: a disclosure element
            rows += (
                f"<details><summary>+ {len(manifest) - ROWS} more</summary>"
                f"<table><tbody>{''.join(manifest[ROWS:])}</tbody></table></details>"
            )
        reason = a.get("reason") or "(no reason given)"
        said = f"“{e(reason)}”"
        if len(reason) > REASON_MAX:
            said = (
                f"“{e(reason[:REASON_MAX])}…”<details><summary>Show full reason</summary>"
                f"<p>“{e(reason)}”</p></details>"
            )
        audience = a.get("audience", [])
        people = sum(1 for x in audience if x.get("principal") == "interactive")
        agents = len(audience) - people
        chips = "<ul class=chips aria-label=Audience>" + "".join(
            f"<li>{e(_chip(x))}</li>" for x in audience[:CHIPS]
        ) + "</ul>"
        if len(audience) > CHIPS:
            chips += (
                f"<details><summary>+ {len(audience) - CHIPS} more</summary><ul class=chips>"
                + "".join(f"<li>{e(_chip(x))}</li>" for x in audience[CHIPS:])
                + "</ul></details>"
            )
        consequence = (
            f"<div class=box><p>{e(a['consequence'])}</p></div>" if a.get("consequence") else ""
        )
        terms = ""
        if seconds:
            terms = (
                f"<p class=terms>window would close {_clock(_now() + seconds)} · org policy "
                f"{seconds // 60}:{seconds % 60:02d} · close early at any time</p>"
            )
        blocked = a.get("blocked")
        if blocked:  # R5: the approve acts are absent, replaced by the red line
            acts = f"<p class=alarm role=status>{e(blocked)}</p>"
        elif armed:
            acts = "<button name=step value=confirm class=act>Confirm signature</button>"
        else:
            acts = "<button name=step value=arm class=act>Sign and approve</button>"
        if self.gate:  # Deny is gate.confirm's; approve.pending has no deny (capabilities.md §4)
            acts += "<button name=step value=deny>Deny</button>"
        if seconds and not armed and not blocked:
            acts += "<button name=step value=arm_once class=ghost>Approve without a window</button>"
        return (
            "<!doctype html><html lang=en><head><meta charset=utf-8>"
            '<meta name=viewport content="width=device-width,initial-scale=1">'
            # §2.3's 10 s revert, without script: the armed page reloads itself after the arm
            # lapses, and the server (which enforces the 10 s regardless) answers un-armed.
            # Escape and focus-loss need script; the baseline has none (design-gap #119).
            + (f'<meta http-equiv=refresh content="{ARM_SECONDS}">' if armed else "")
            + f"<title>egzos · presence</title><style>{_tokens_css()}{TAP_STYLE}</style></head>"
            "<body><main>"
            f"<p class=shell>egzos · container {e(self.container)} · {e(self.host)}</p>"
            f"<p class=shell>you · {e(OWNER)} · principal: interactive · present since "
            f"{e(_since(self.opened))}</p>"
            # §2.2 item 2 defines the reference line for a proposal; the item-promotion tap's
            # line is design-gap #122, so it renders none rather than an invented one.
            + (f"<p class=ref>PROPOSAL <code title=\"{e(a['subject'])}\">"
               f"{e(short_id(a['subject']))}</code> · filed {e(a.get('filed') or '')}</p>"
               if self.gate else "")
            # §2.2 item 8: initial focus on the page heading, never on an act.
            + f"<h1 tabindex=-1 autofocus>{e(a['title'])}</h1>"
            # §2.2 item 4 is the requester's stated reason: a proposal has one; approve.pending is
            # the owner's own act and has none to state (design-gap #122).
            + (f"<p><span class=attr>{e(a.get('requester', 'you'))} states:</span> {said}</p>"
               if self.gate else "")
            + f"<h2>what moves</h2>{rows}"
            f"<h2>who will see it at {e(a.get('dest', a['to']))}</h2>"
            f"<p>{people} people · {agents} agents · resolved from token grants and scope "
            f"membership</p>{chips}{consequence}"
            "<section role=region aria-labelledby=presence-h class=box>"
            f"<h2 id=presence-h>presence</h2><p>{e(presence_text(a, seconds))}</p>{terms}"
            + (f"<p class=note aria-live=polite>{e(note)}</p>" if note else "")
            + (f"<p class=alarm role=status>{e(error)}</p>" if error else "")
            + f"<form method=post>{acts}</form></section></main></body></html>"
        )

    def outcome_page(self, text: str, back: str | None = None) -> str:
        link = f'<p><a href="{_e(back)}">Return to pending</a></p>' if back else ""
        return (
            "<!doctype html><html lang=en><head><meta charset=utf-8>"
            f"<title>egzos · presence</title><style>{_tokens_css()}{TAP_STYLE}</style></head>"
            f"<body><main><div class=box><p role=status>{_e(text)}</p></div>{link}</main>"
            "</body></html>"
        )

    # -- the decision, independent of which server hosts the page ------------------------------------
    def live(self, path: str) -> bool:
        return (
            self.outcome is None
            and path.startswith("/tap/")
            and secrets.compare_digest(path[len("/tap/"):], self.token)
        )

    def get(self) -> tuple[int, str]:
        return 200, self.page(armed=self.armed_until > _now())

    def post(self, step: str) -> tuple[int, str]:
        """Apply one press. On a decision, the host's `decide` performs it and the page shows the
        container's answer in §13's canonical copy."""
        if step == "deny" and self.gate:
            self.outcome = "denied"
            return self._answer()
        if self.act.get("blocked") and step in ("arm", "arm_once", "confirm"):
            return 200, self.page(armed=False)
        if step in ("arm", "arm_once"):
            self.armed_until = _now() + ARM_SECONDS
            self.armed_mode = "once" if step == "arm_once" else "window"
            return 200, self.page(armed=True, note=TAP_COPY["act.confirm.sr"])
        if step == "confirm" and self.armed_until > _now():
            self.windowed = self.armed_mode == "window"
            self.outcome = "approved"
            return self._answer()
        # R9: a confirm after the 10 s, or any other press, reverts to Sign and approve, un-armed.
        self.armed_until = 0.0
        return 200, self.page(armed=False)

    def _answer(self) -> tuple[int, str]:
        """The container's answer; or, if the act failed, R9's error row: back to ready, nothing
        changed, the page still live so the person can try again."""
        try:
            return 200, self.outcome_page(self._decided())
        except Exception:
            self.outcome = None
            self.armed_until = 0.0
            return 200, self.page(armed=False, error=TAP_COPY["act.error"])

    def _decided(self) -> str:
        if self.decide is not None:
            return self.decide(self.outcome, self.windowed)
        seconds = window_seconds()
        closes = (_iso(_now() + seconds)
                  if self.outcome == "approved" and self.windowed and seconds else None)
        return outcome_text(self.act, self.outcome or "", closes=closes)

    def handler(self):
        tap = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "egzos"
            sys_version = ""

            def log_message(self, *args):
                return

            def _send(self, status: int, body: str) -> None:
                send_page(self, status, body)

            def do_GET(self):  # noqa: N802
                if not tap.live(self.path):
                    return self._send(404, empty_page())
                self._send(*tap.get())

            def do_POST(self):  # noqa: N802
                if not tap.live(self.path):
                    return self._send(404, empty_page())
                if not same_origin(self.headers):
                    return self._send(403, "<p>Refused.</p>")
                self._send(*tap.post(read_step(self)))

        return Handler


def empty_page() -> str:
    """R11: one page for an unknown, foreign, expired or used token — §13 `tap.empty` as the
    heading, the body empty, nothing on it depending on which cause it was."""
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        f"<title>egzos · presence</title><style>{_tokens_css()}{TAP_STYLE}</style></head>"
        f"<body><main><h1 tabindex=-1 autofocus>{_e(TAP_COPY['tap.empty'])}</h1></main>"
        "</body></html>"
    )


def same_origin(headers) -> bool:
    """A state-changing request must name this origin. A MISSING Origin is refused too: every
    browser sends one on a form POST, so its absence means something that is not a browser form."""
    return headers.get("Origin") == f"http://{headers.get('Host', '')}"


def read_step(request: BaseHTTPRequestHandler) -> str:
    # Bounded both ways: a negative length would read until the sender closed the connection.
    length = max(0, min(int(request.headers.get("Content-Length") or 0), 4096))
    return parse_qs(request.rfile.read(length).decode()).get("step", [""])[0]


def send_page(request: BaseHTTPRequestHandler, status: int, body: str) -> None:
    data = body.encode()
    request.send_response(status)
    request.send_header("Content-Type", "text/html; charset=utf-8")
    request.send_header("Content-Length", str(len(data)))
    request.send_header("Cache-Control", "no-store")
    request.send_header("Referrer-Policy", "no-referrer")
    request.send_header("X-Frame-Options", "DENY")
    request.send_header(
        "Content-Security-Policy",
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
        "frame-ancestors 'none'; base-uri 'none'",
    )
    request.end_headers()
    request.wfile.write(data)
