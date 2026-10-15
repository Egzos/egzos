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
from functools import cache
from importlib import resources
from types import MappingProxyType

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, FunctionLoader, StrictUndefined

from egzos._types import AS_USER_CODE_LENGTH
from egzos.authz import continuation, metadata
from egzos.authz.presence import _tokens_css

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
    return _tokens_css() + STYLE


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
