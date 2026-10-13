# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The AS's own pages, rendered (`spec/design/consent.md`; authorization-server.md §5.3, §11.7, §11.8).

The look is `consent.md`'s and the truths are the contract's. The pages are this module's templates,
in `src/egzos/authz/templates/`, the AS's own (consent.md's Consumers line). The lifeboat's shell
partial `_shell.html` is imported by name from `egzos.web` and never copied (§16, §18). Every string
comes from `COPY`, keyed as consent.md §13 keys it and rendered verbatim, so a new string needs a
spec revision. Everything a page renders from outside this module (a container name, a host, an
entry the caller typed) is data and goes through Jinja's autoescape.

Rendered here, and mounted by nobody yet (the router's holds, `router.HELD`):

- `failure`: §5.3's uniform pre-trust page (consent.md §2.5). One body for every cause, since the
  function takes no cause, and `FAILURE_STATUS` (400, [0.3 · 23]) for all of them. It names no
  client and echoes no request parameter.
- `login`: §11.7's form (consent.md §2.1, R2 `ready` and `error (credential)`). Its `continue` sits
  in the one position §11.7 permits, a hidden input, and only after `continuation.resolve` has
  matched it. A value that does not come back from `resolve` unchanged raises instead of rendering:
  §11.7 says a value failing D-C5 never reaches the carrier, and that the GET answers it with a 303
  and no page. The secret field never carries a value.
- `device`: §11.8's entry form (consent.md §2.2, R3 `ready` and the failure row). It takes no
  prefill, so a `user_code` query parameter has nowhere to go ([0.3 · 21]).

The consent screen's vocabulary is here too, ahead of its renderer: its §13 strings in `COPY`;
`ScopeLabel`, what R8 shows for one granted node id; `is_wide`, D-C1's table over an `Offer`; and
§5's formats (`countdown`, `cut_name`, `short_id`, `origin`, `role_line`).

A failed attempt and a throttle-refused one render the same bytes, because neither function takes
the cause (R2 and R3's refused rows; §11.7, §11.8). Which status a failed `/login` or `/device`
answers with is the router's: the contract fixes only that it is one status for every cause.

`HEADERS` are §10 and §18's, for every response these pages make. `css()` is the pages' one
stylesheet, the tokens followed by `STYLE`, for the host to serve at the path it passes as
`stylesheet`. It follows the tap page's `tap_css()`, so the CSP stays `style-src 'self'` and no
page carries inline style.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from importlib import resources
from types import MappingProxyType
from urllib.parse import urlsplit

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, FunctionLoader, StrictUndefined

from egzos._types import (
    AS_SCOPE_ALL_NODES,
    AS_SCOPE_NODE_PREFIX,
    AS_USER_CODE_LENGTH,
    RING_RANK,
    ROLE_BUNDLES,
)
from egzos.authz import continuation, metadata, redirects
from egzos.authz.grant import Offer
from egzos.authz.presence import tokens_css

#: consent.md §13, the keys these pages render, verbatim.
COPY: Mapping[str, str] = MappingProxyType(
    {
        "title.login": "egzos · sign in",
        "title.device": "egzos · device code",
        "title.failure": "egzos",
        "shell.container": "egzos · container {name} · {host}",
        "login.title": "Sign in to container {name}.",
        "login.secret": "Container secret",
        "login.act": "Sign in",
        "login.error": "That didn't work. Try again.",
        "device.title": "Enter the code your terminal shows.",
        "device.label": "Code",
        "device.placeholder": "XXXX-XXXX",
        "device.act": "Continue",
        "device.expiry": "Codes expire a few minutes after your terminal shows them.",
        "device.error": "That code isn't valid or has expired.",
        "failure.title": "This request can't be completed.",
        "title.consent": "egzos · grant request",
        "shell.viewer": "you · {user} · principal: interactive · signed in {hhmm}",
        "ref.request": "GRANT REQUEST · {client} · requested {time}",
        "ref.code": "· code {code}",
        "consent.title": "{Client} asks for a token to your container.",
        "client.label": "client",
        "client.id": "id",
        "client.redirect": "redirects to {origin}",
        "client.local": "local development origin",
        "client.registered": "registered {date}",
        "kind.browser": "browser",
        "kind.device": "device",
        "kind.mcp": "mcp",
        "principal.client": (
            "principal: client — this token acts on its own. It can propose, never approve. "
            "Human-only acts stay with you."
        ),
        "principal.interactive": (
            "principal: interactive — this token acts as you while you are present. "
            "Human-only acts still need your tap."
        ),
        "section.caps": "capabilities",
        "section.scopes": "scopes",
        "section.expiry": "expiry",
        "cap.fetch": "fetch — reading context; downloading artifacts is fetch",
        "cap.remember": "remember — writing, in the same scope only",
        "cap.organize": "organize — moving items between containers",
        "cap.publish": "publish — proposing a wider audience",
        "cap.curate": "curate — quarantining items, and lifting quarantine",
        "cap.admin": "admin — creating containers above a node's structure floor",
        "role.bundle": "role · {bundle}",
        "role.custom": "custom set",
        "scope.line": "{scope} · ring {ring}",
        "scope.coverage": (
            "Coverage reaches everything under {scope} — including containers created there later."
        ),
        "scope.all": (
            "Consequence. This token reaches everything in this container, including containers "
            "created later."
        ),
        "scope.more": "+ {n} more",
        "expiry.at": "expires {date} {time} · in {left}",
        "expiry.clamped": "shortened to the container's maximum",
        "existing": (
            "This client already holds {n} live tokens · latest minted {date}. "
            "Authorizing mints another."
        ),
        "narrow.hint": (
            "Want to grant less than this? Deny, then mint it yourself: egzos token mint"
        ),
        "wide.note": "This is a wide grant. Authorizing takes two presses.",
        "act.authorize": "Authorize",
        "act.confirm": "Confirm authorization",
        "act.confirm.sr": "Press again to confirm.",
        "act.deny": "Deny",
        "act.error": "That didn't go through. Nothing was minted. Try again.",
        "invalid": "This request is no longer valid.",
    }
)

#: §5.3 [0.3 · 23]: one status for every cause of the uniform page.
FAILURE_STATUS = 400

#: consent.md §10 and §18, on every response these pages make. `nosniff` is added on the
#: lifeboat's precedent and loosens nothing.
HEADERS: Mapping[str, str] = MappingProxyType(
    {
        "Referrer-Policy": "same-origin",
        "Cache-Control": "no-store",
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": (
            "default-src 'none'; style-src 'self'; img-src 'self'; form-action 'self'; "
            "frame-ancestors 'none'"
        ),
    }
)

#: consent.md §5: the code is 8 characters, shown `XXXX-XXXX`, so an entry is at most 9.
DEVICE_ENTRY_MAX = AS_USER_CODE_LENGTH + 1

#: The pages' own rules over `tokens.css`: tokens only, radius from the token, no motion (§5–§9).
STYLE = """
body{margin:0;background:var(--egz-canvas);color:var(--egz-ink);font-family:var(--egz-font-ui);
 line-height:var(--egz-lh)}
.frame{max-width:480px;margin:var(--egz-sp-6) auto;padding:var(--egz-sp-4) var(--egz-sp-5);
 border:var(--egz-bw) solid var(--egz-rule);box-shadow:var(--egz-off-lg) var(--egz-off-lg) 0
 var(--egz-shadow-ink);border-radius:var(--egz-radius)}
.shell{font-family:var(--egz-font-mono);font-size:var(--egz-fs-2);
 border-bottom:var(--egz-hair) solid var(--egz-rule-soft);padding-bottom:var(--egz-sp-3)}
h1{font-size:var(--egz-fs-6);font-weight:var(--egz-w-semibold)}
form{display:flex;flex-direction:column;gap:var(--egz-sp-3)}
input{min-height:44px;padding:0 var(--egz-sp-3);border:var(--egz-bw) solid var(--egz-ink);
 border-radius:var(--egz-radius);background:var(--egz-canvas);color:var(--egz-ink);
 font:inherit}
input.code{font-family:var(--egz-font-mono);font-size:var(--egz-fs-5);
 letter-spacing:var(--egz-tracking-caps);text-transform:uppercase}
button{-webkit-appearance:none;appearance:none;min-height:44px;padding:0 var(--egz-sp-4);
 border:var(--egz-bw) solid var(--egz-rule);border-radius:var(--egz-radius);
 background:var(--egz-canvas);color:var(--egz-ink);font:inherit;
 box-shadow:var(--egz-off) var(--egz-off) 0 var(--egz-shadow-ink)}
button:active{transform:translate(var(--egz-off),var(--egz-off));box-shadow:none}
button:focus-visible,input:focus-visible,h1:focus-visible{outline:var(--egz-focus);
 outline-offset:3px}
"""

_TEMPLATES = resources.files("egzos.authz").joinpath("templates")


def css() -> str:
    """The pages' whole stylesheet: the tokens and `STYLE`, for a host that serves it."""
    return tokens_css() + STYLE


def _shell_partial(name: str) -> str | None:
    # The lifeboat's partial and nothing else of the lifeboat's: imported, never forked (§16).
    if name != "_shell.html":
        return None
    return resources.files("egzos.web").joinpath("templates", name).read_text(encoding="utf-8")


@cache
def _env() -> Environment:
    return Environment(
        loader=ChoiceLoader([FileSystemLoader(str(_TEMPLATES)), FunctionLoader(_shell_partial)]),
        autoescape=True,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )


def _shell(container: str, host: str) -> dict[str, object]:
    # R1 `signed-out`: the container line only. No viewer line and no nav before anyone is known.
    line = COPY["shell.container"].format(name=container, host=host)
    return {
        "container_line": line,
        "viewer_line": None,
        "window": None,
        "nav": None,
        "scheme": None,
    }


def _render(
    template: str, *, title: str, container: str, host: str, stylesheet: str, **context: object
) -> str:
    for value in (container, host, stylesheet):
        if not isinstance(value, str):
            raise TypeError("container, host and stylesheet are strings")
    return (
        _env()
        .get_template(template)
        .render(
            C=COPY,
            title=COPY[title],
            shell=_shell(container, host),
            stylesheet=stylesheet,
            **context,
        )
    )


def failure(*, container: str, host: str, stylesheet: str) -> str:
    """§5.3's uniform page. It takes no cause, so no cause can reach it. Send with
    `FAILURE_STATUS` and `HEADERS`."""
    return _render(
        "as_failure.html",
        title="title.failure",
        container=container,
        host=host,
        stylesheet=stylesheet,
    )


def login(
    *, container: str, host: str, stylesheet: str, carry: str | None = None, failed: bool = False
) -> str:
    """§11.7's form: R2 `ready`, or, with `failed`, `error (credential)`. `carry` is
    `continuation.resolve`'s answer for the request's `continue`, or None when there was none.
    Raises `ValueError` for anything else, because §11.7 lets only a matched value reach the
    carrier."""
    if carry is not None and continuation.resolve(carry) != carry:
        raise ValueError("continue must be matched by continuation.resolve before it is carried")
    return _render(
        "as_login.html",
        title="title.login",
        container=container,
        host=host,
        stylesheet=stylesheet,
        action=metadata.LOGIN_PATH,
        heading=COPY["login.title"].format(name=container),
        carry=carry,
        failed=failed is True,
    )


def _kept(entry: object) -> str:
    # R3 keeps the field on a failure. The value is the caller's own, re-shown to the same caller,
    # cut to what the field accepts. Characters outside printable ASCII are dropped, since no code
    # contains one and a lone surrogate could not be encoded into the page.
    if not isinstance(entry, str):
        return ""
    return "".join(ch for ch in entry if "\x20" <= ch <= "\x7e")[:DEVICE_ENTRY_MAX]


def device(
    *, container: str, host: str, stylesheet: str, failed: bool = False, entry: str | None = None
) -> str:
    """§11.8's entry form: R3 `ready`, or, with `failed`, the one failure row for every cause, with
    `entry` (the POSTed code) kept in the field. There is no prefill parameter ([0.3 · 21])."""
    is_failed = failed is True
    return _render(
        "as_device.html",
        title="title.device",
        container=container,
        host=host,
        stylesheet=stylesheet,
        action=metadata.DEVICE_ENTRY_PATH,
        max_entry=DEVICE_ENTRY_MAX,
        failed=is_failed,
        kept=_kept(entry) if is_failed else "",
    )


# --- §11: the consent screen's vocabulary ---------------------------------------------------------

#: consent.md §5: the client name's cut (R4) and the scopes shown before `+ N more` (R8 `partial`).
NAME_MAX = 64
SCOPES_SHOWN = 8
#: §2.3 item 7's rendering of `*`. It is not a §13 key, so it is held here by name (#259).
WHOLE_CONTAINER = "whole container"

#: `Token.scopes`' spelling of the whole container: `node:*` without its prefix (§7 consequence 3).
_ALL = AS_SCOPE_ALL_NODES.removeprefix(AS_SCOPE_NODE_PREFIX)
#: D-C1: a grant asking for either of these is wide.
_WIDE_CAPS = frozenset({"curate", "admin"})
_RANK: Mapping[str, int] = MappingProxyType(dict(RING_RANK))
#: D-C1 and R8: rings at `org` or wider.
_WIDE_RANK = RING_RANK["org"]


@dataclass(frozen=True)
class ScopeLabel:
    """What R8 renders for one granted node id: the node's `type` (its ring word, or `user` at the
    personal root) and its `name`. The caller reads both from the node the id names. Nothing here
    resolves an id."""

    type: str
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.type, str) or not isinstance(self.name, str):
            raise TypeError("a scope label is a node's type and name")

    @property
    def ref(self) -> str:
        """`scope.line`'s and `scope.coverage`'s `<scope>`: `project:atlas`."""
        return f"{self.type}:{self.name}"

    @property
    def flagged(self) -> bool:
        """R8 `ready (org or wider)`: a known ring at `org` or past it."""
        rank = _RANK.get(self.type)
        return rank is not None and rank >= _WIDE_RANK

    @property
    def wide(self) -> bool:
        """D-C1's scope rows: `org` or wider, or no ring rank. The personal root `user` has none
        (container.md §2). A ring word this build does not know has none either, and is taken as
        wide, the side that asks for the second press (#259)."""
        return self.flagged or self.type not in _RANK


def is_wide(offer: Offer, labels: Mapping[str, ScopeLabel]) -> bool:
    """D-C1's table over what will be minted (§11.2). `labels` names every granted node id but `*`,
    and a missing one raises `ValueError` rather than reading as narrow. No-expiry never occurs
    here, since an AS grant always expires (§11.5)."""
    if not isinstance(offer, Offer):
        raise TypeError("D-C1 reads an offer")
    scoped = [s for s in offer.scopes if s != _ALL]
    if any(not isinstance(labels.get(s), ScopeLabel) for s in scoped):
        raise ValueError("every granted node id has its label")
    return (
        offer.principal == "interactive"
        or any(c in _WIDE_CAPS for c in offer.capabilities)
        or _ALL in offer.scopes
        or any(labels[s].wide for s in scoped)
    )


def countdown(seconds: int) -> str:
    """§5 Formats, the `N d` of `expiry.at`: under a day `N h`, under an hour `N min`, and never
    `0 min` for a lifetime that has not run out."""
    if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds <= 0:
        raise ValueError("a countdown is a positive number of seconds")
    if seconds >= 86400:
        return f"{seconds // 86400} d"
    if seconds >= 3600:
        return f"{seconds // 3600} h"
    return f"{max(1, seconds // 60)} min"


def cut_name(name: str) -> str:
    """R4 `ready (long client name)`: cut at `NAME_MAX` characters, then `…`. The whole name goes
    in `title`, which is the renderer's."""
    return name if len(name) <= NAME_MAX else name[:NAME_MAX] + "…"


def short_id(client_id: str) -> str:
    """§5 Formats: `cli_01J7 … 9KQ2`, the first 8 and the last 4. An id of 12 or fewer shows
    whole, since cutting it would hide nothing."""
    return client_id if len(client_id) <= 12 else f"{client_id[:8]} … {client_id[-4:]}"


def origin(uri: str) -> tuple[str, bool]:
    """R5's `<origin>`: scheme, host and port, never the whole URI, so no path or query reaches the
    page. True beside it for §5.2's literal loopback hosts, the only `local development origin` a
    conforming container holds (`localhost` is refused at registration, [0.3 · 22])."""
    parts = urlsplit(uri)
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    port = f":{parts.port}" if parts.port is not None else ""
    return f"{parts.scheme}://{host}{port}", host in redirects.LOOPBACK_HOSTS


def role_line(capabilities: tuple[str, ...]) -> str:
    """R7: `role · <bundle>` when the set is exactly a bundle, else `custom set`. The token itself
    carries capabilities, never the bundle's name (§7 consequence 1)."""
    held = frozenset(capabilities)
    for name, caps in ROLE_BUNDLES.items():
        if caps == held:
            return COPY["role.bundle"].format(bundle=name)
    return COPY["role.custom"]
