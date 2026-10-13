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

- `consent`: §11's screen (consent.md §2.3, R4 to R11) for one decided-on request: the grant is
  `grant.Offer`'s fields and nothing else, so what renders is what the mint produces (§11.2). The
  expiry renders as `at` plus the offer's clamped lifetime, with `expiry.clamped` when the request
  asked for more (§11.5). D-C1's table decides `wide`, and a wide grant's Authorize arms (`arm`)
  before it confirms. The arm token, its 10 s and the form's hidden fields (the request's identity,
  the session's form token) are the caller's, as the decision is. The page only renders them.

A failed attempt and a throttle-refused one render the same bytes, because neither function takes
the cause (R2 and R3's refused rows; §11.7, §11.8). Which status a failed `/login` or `/device`
answers with is the router's: the contract fixes only that it is one status for every cause.

`HEADERS` are §10 and §18's, for every response these pages make. `css()` is the pages' one
stylesheet, the tokens followed by `STYLE`, for the host to serve at the path it passes as
`stylesheet`. It follows the tap page's `tap_css()`, so the CSP stays `style-src 'self'` and no
page carries inline style.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from importlib import resources
from types import MappingProxyType
from urllib.parse import urlsplit

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, FunctionLoader, StrictUndefined

from egzos._types import (
    AS_SCOPE_ALL_NODES,
    AS_SCOPE_NODE_PREFIX,
    AS_USER_CODE_LENGTH,
    CAPABILITIES,
    RING_RANK,
    ROLE_BUNDLES,
)
from egzos.authz import continuation, metadata, redirects
from egzos.authz.grant import Offer
from egzos.authz.presence import tokens_css
from egzos.authz.screen import ClientEntry, ExistingTokens

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
button:focus-visible,input:focus-visible,h1:focus-visible,a:focus-visible{
 outline:var(--egz-focus);outline-offset:3px}
.frame--consent{max-width:640px}
.ref{font-family:var(--egz-font-mono);font-size:var(--egz-fs-1);text-transform:uppercase;
 letter-spacing:var(--egz-tracking-caps)}
code,.mono{font-family:var(--egz-font-mono)}
section,.client,.acts{margin:var(--egz-sp-5) 0}
.box,.framed{border:var(--egz-bw) solid var(--egz-rule);padding:var(--egz-sp-4) var(--egz-sp-5);
 box-shadow:var(--egz-off) var(--egz-off) 0 var(--egz-shadow-ink);border-radius:var(--egz-radius)}
.client,.lines,.stamps{list-style:none;padding:0}
.lines li{border-bottom:var(--egz-hair) solid var(--egz-rule-soft)}
.stamps{display:flex;flex-wrap:wrap;gap:var(--egz-sp-2)}
.stamp{font-family:var(--egz-font-mono);font-size:var(--egz-fs-1);text-transform:uppercase;
 padding:0 var(--egz-sp-1);border:var(--egz-hair) solid var(--egz-ink);
 border-radius:var(--egz-radius)}
.stamp--solid{background:var(--egz-ink);color:var(--egz-canvas)}
.chip--wide{border:var(--egz-bw) solid var(--egz-ink);padding:0 var(--egz-sp-1)}
.more{display:inline-block;min-height:44px;line-height:44px;color:var(--egz-ink)}
.acts{flex-direction:row;flex-wrap:wrap}
button.act{background:var(--egz-act);color:var(--egz-act-on);border-color:var(--egz-act)}
.alarm{color:var(--egz-alarm)}
@media (max-width:480px){.acts{flex-direction:column}}
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


def _shell(container: str, host: str, viewer_line: str | None) -> dict[str, object]:
    # R1: `signed-out` is the container line only; `ready` (consent) adds the viewer line. No nav
    # on any of these pages, which have one job each.
    line = COPY["shell.container"].format(name=container, host=host)
    return {
        "container_line": line,
        "viewer_line": viewer_line,
        "window": None,
        "nav": None,
        "scheme": None,
    }


def _render(
    template: str,
    *,
    title: str,
    container: str,
    host: str,
    stylesheet: str,
    viewer_line: str | None = None,
    **context: object,
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
            shell=_shell(container, host, viewer_line),
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


# --- §11: the consent screen ----------------------------------------------------------------------

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
#: A hidden field the caller names: a short lowercase word, never one of the acts' own fields.
_FIELD = re.compile(r"[a-z][a-z_]{0,31}")
_ACT_FIELDS = frozenset({"step", "arm"})
_ARM = re.compile(r"[A-Za-z0-9_-]{16,128}")


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
    """D-C1's table. No-expiry never occurs here, since an AS grant always expires (§11.5)."""
    return (
        offer.principal == "interactive"
        or any(c in _WIDE_CAPS for c in offer.capabilities)
        or any(s == _ALL or labels[s].wide for s in offer.scopes)
    )


def _aware(at: object) -> datetime:
    if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise TypeError("the consent page's times are aware datetimes")
    return at


def _stamp(value: str, at: datetime) -> datetime:
    # A stored `…Z` stamp, shown in the zone `at` is in. One that does not parse raises
    # `ValueError`, and the caller answers with R12's error card rather than a guessed date.
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(at.tzinfo)


def _left(seconds: int) -> str:
    # §5 Formats: `in N d`; under a day `in N h`; under an hour `in N min`.
    if seconds >= 86400:
        return f"{seconds // 86400} d"
    if seconds >= 3600:
        return f"{seconds // 3600} h"
    return f"{max(1, seconds // 60)} min"


def _cut(name: str) -> str:
    return name if len(name) <= NAME_MAX else name[:NAME_MAX] + "…"


def _short_id(client_id: str) -> str:
    # §5 Formats: the first 8, ` … `, the last 4; the whole id in `title`.
    return client_id if len(client_id) <= 12 else f"{client_id[:8]} … {client_id[-4:]}"


def _origin(uri: str) -> tuple[str, bool]:
    """Scheme, host and port: the origin R5 shows, never the whole URI. True for §5.2's literal
    loopback hosts, the only `local development origin` a conforming container holds."""
    parts = urlsplit(uri)
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    port = f":{parts.port}" if parts.port is not None else ""
    return f"{parts.scheme}://{host}{port}", host in redirects.LOOPBACK_HOSTS


def _bundle(capabilities: tuple[str, ...]) -> str:
    held = frozenset(capabilities)
    for name, caps in ROLE_BUNDLES.items():
        if caps == held:
            return COPY["role.bundle"].format(bundle=name)
    return COPY["role.custom"]


def _fields(fields: Mapping[str, str]) -> list[tuple[str, str]]:
    pairs = sorted(fields.items())
    for name, value in pairs:
        if not isinstance(name, str) or not _FIELD.fullmatch(name) or name in _ACT_FIELDS:
            raise ValueError("a hidden field is a short lowercase name, never step or arm")
        if not isinstance(value, str):
            raise TypeError("a hidden field's value is a string")
    return pairs


def consent(
    *,
    container: str,
    host: str,
    stylesheet: str,
    viewer: str,
    signed_in: datetime,
    at: datetime,
    client: ClientEntry,
    offer: Offer,
    labels: Mapping[str, ScopeLabel],
    existing: ExistingTokens,
    fields: Mapping[str, str],
    redirect_uri: str | None = None,
    user_code: str | None = None,
    requested_lifetime_seconds: int | None = None,
    more: str | None = None,
    arm: str | None = None,
    failed: bool = False,
    invalid: bool = False,
) -> str:
    """§2.3 for `offer`, requested by `client` at `at`, rendered for the signed-in `viewer`.

    `labels` names every granted node id but `*`. `redirect_uri` is the request's, already matched
    against `client`'s registration (§5). It is required for a `browser` or `mcp` client and
    refused for a `device` one, which shows `user_code` instead. `more` is the request's own
    `/authorize` address with `full=1`, matched by `continuation.resolve`: when it is given and
    there are more than `SCOPES_SHOWN` scopes, R8 renders `partial`, and without it every scope
    renders. `arm` is the server-held token of a wide grant's first press (R11 `confirming`).
    `failed` is R11 `error (mint failed)`. `invalid` is R4 `invalid`, with no acts. Send with
    `HEADERS`."""
    signed_in, at = _aware(signed_in), _aware(at)
    if not isinstance(client, ClientEntry) or not isinstance(offer, Offer):
        raise TypeError("the screen renders a registry entry and an offer")
    if not isinstance(viewer, str) or not isinstance(existing, ExistingTokens):
        raise TypeError("viewer is a string and existing is §11.3's read")
    scoped = [s for s in offer.scopes if s != _ALL]
    if any(not isinstance(labels.get(s), ScopeLabel) for s in scoped):
        raise ValueError("every granted node id renders with its label")
    if client.kind == "device":
        if redirect_uri is not None or not isinstance(user_code, str):
            raise ValueError("a device request shows its user_code and redirects nowhere")
        redirect = None
    else:
        if (
            not isinstance(redirect_uri, str)
            or user_code is not None
            or not redirects.match_any(redirect_uri, list(client.redirect_uris))
        ):
            raise ValueError("a redirecting client's request names a registered redirect_uri")
        redirect = _origin(redirect_uri)
    if more is not None and continuation.resolve(more) != more:
        raise ValueError("more is the request's own /authorize address")
    wide = is_wide(offer, labels)
    if arm is not None and (not wide or not isinstance(arm, str) or not _ARM.fullmatch(arm)):
        raise ValueError("only a wide grant arms, with a server-held token")
    clamped = (
        isinstance(requested_lifetime_seconds, int)
        and requested_lifetime_seconds > offer.lifetime_seconds
    )

    name = _cut(client.client_name)
    reference = COPY["ref.request"].format(client=name, time=at.strftime("%H:%M:%S"))
    if user_code is not None:
        reference += " " + COPY["ref.code"].format(code=user_code)
    lines = sorted(
        (labels[s] for s in scoped), key=lambda label: not label.flagged
    )  # R8: org or wider first, otherwise in the grant's order
    shown = lines[:SCOPES_SHOWN] if more is not None else lines
    until = at + timedelta(seconds=offer.lifetime_seconds)
    latest = existing.latest_created_at
    return _render(
        "as_consent.html",
        title="title.consent",
        container=container,
        host=host,
        stylesheet=stylesheet,
        viewer_line=COPY["shell.viewer"].format(user=viewer, hhmm=signed_in.strftime("%H:%M")),
        frame="frame frame--consent",
        action=metadata.AUTHORIZE_PATH,
        reference=reference,
        heading=COPY["consent.title"].format(Client=name),
        full_name=client.client_name,
        client_name=name,
        client_id=client.client_id,
        short_id=_short_id(client.client_id),
        redirect=(
            None
            if redirect is None
            else COPY["client.redirect"].format(origin=redirect[0])
            + (" · " + COPY["client.local"] if redirect[1] else "")
        ),
        registered=COPY["client.registered"].format(
            date=_stamp(client.registered_at, at).strftime("%Y-%m-%d")
        ),
        kind=COPY["kind." + client.kind],
        interactive=offer.principal == "interactive",
        stamps=[(c, c in offer.capabilities) for c in CAPABILITIES],
        caps=[(c, COPY["cap." + c][len(c) :]) for c in offer.capabilities],
        caps_wide=any(c in _WIDE_CAPS for c in offer.capabilities),
        role=_bundle(offer.capabilities),
        everything=_ALL in offer.scopes,
        scopes=[
            (
                COPY["scope.line"].format(scope=label.ref, ring=label.type),
                COPY["scope.coverage"].format(scope=label.ref),
                label.flagged,
            )
            for label in shown
        ],
        scopes_wide=_ALL in offer.scopes or any(label.wide for label in lines),
        whole=WHOLE_CONTAINER,
        more=(more, COPY["scope.more"].format(n=len(lines) - len(shown)))
        if len(shown) < len(lines)
        else None,
        expires_iso=until.isoformat(),
        expires=COPY["expiry.at"].format(
            date=until.strftime("%Y-%m-%d"),
            time=until.strftime("%H:%M:%S"),
            left=_left(offer.lifetime_seconds),
        ),
        clamped=clamped,
        # R10: a live count with no readable stamp still renders, dated `—` (#259).
        existing=None
        if existing.live < 1
        else COPY["existing"].format(
            n=existing.live,
            date="—" if latest is None else _stamp(latest, at).strftime("%Y-%m-%d"),
        ),
        hint=COPY["narrow.hint"].removesuffix("egzos token mint"),
        wide=wide,
        fields=_fields(fields),
        arm=arm,
        failed=failed is True,
        invalid=invalid is True,
    )
