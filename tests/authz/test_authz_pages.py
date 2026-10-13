# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The AS's own pages: the uniform failure page, /login and /device (authz/pages.py)."""

from __future__ import annotations

import inspect
import re
from html.parser import HTMLParser
from importlib import resources
from pathlib import Path

import pytest

from egzos.authz import continuation, metadata, pages

SPEC = Path(__file__).resolve().parents[2] / "spec" / "design" / "consent.md"
BOX = {"container": "home", "host": "box.example:8443", "stylesheet": "/as.css"}


class Tags(HTMLParser):
    """Every start tag with its attributes, and the text outside tags."""

    def __init__(self, page: str) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.text: list[str] = []
        self.feed(page)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.text.append(data.strip())

    def find(self, tag: str, **match: str) -> list[dict[str, str | None]]:
        return [
            a for t, a in self.tags if t == tag and all(a.get(k) == v for k, v in match.items())
        ]


# --- the copy and the headers ---------------------------------------------------------------------


def test_every_string_is_consent_md_s13_verbatim() -> None:
    spec = SPEC.read_text(encoding="utf-8")
    table = spec[spec.index("## 13. Copy") : spec.index("## 14.")]
    # Each format field and the placeholder §13 writes in its place.
    fields = {"{host}": "<host:port>", "{hhmm}": "HH:MM", "{time}": "HH:MM:SS", "{n}": "N"}
    fields |= {"{code}": "XXXX-XXXX", "{left}": "N d"}
    for key, value in pages.COPY.items():
        rendered = value
        for field, placeholder in fields.items():
            rendered = rendered.replace(field, placeholder)
        rendered = rendered.replace("{", "<").replace("}", ">")
        assert key in table, key
        assert f"`{rendered}`" in table, key


def test_copy_lacks_only_the_outcome_and_print_keys() -> None:
    # A missing key passes the verbatim test above; this one catches it. The keys left out
    # belong to the outcome, error-card and print renders, which no slice has built yet.
    spec = SPEC.read_text(encoding="utf-8")
    table = spec[spec.index("## 13. Copy") : spec.index("## 14.")]
    keys = set(re.findall(r"(?m)(?:^\| |· )([a-z]+(?:\.[a-z]+)*) (?=\||`)", table)) - {"key"}
    later = {"title.done", "done.title", "done.minted", "denied.title", "denied.at"}
    later |= {"fail.error", "fail.retry", "print.header", "print.footer"}
    assert keys - set(pages.COPY) == later


def test_headers_are_s10_and_s18s() -> None:
    assert pages.HEADERS["Referrer-Policy"] == "same-origin"  # not no-referrer: #130
    assert pages.HEADERS["Cache-Control"] == "no-store"
    assert pages.HEADERS["X-Frame-Options"] == "DENY"
    assert pages.HEADERS["Content-Security-Policy"] == (
        "default-src 'none'; style-src 'self'; img-src 'self'; form-action 'self'; "
        "frame-ancestors 'none'"
    )
    with pytest.raises(TypeError):
        pages.HEADERS["Cache-Control"] = "public"  # type: ignore[index]


def test_css_is_the_tokens_then_the_pages_rules_and_no_literal_colour() -> None:
    sheet = pages.css()
    assert "--egz-ink:" in sheet and sheet.endswith(pages.STYLE)
    assert "#" not in pages.STYLE and "rgb" not in pages.STYLE


def test_the_shell_partial_is_the_lifeboats_imported_not_forked() -> None:
    lifeboat = resources.files("egzos.web").joinpath("templates", "_shell.html")
    assert pages._shell_partial("_shell.html") == lifeboat.read_text(encoding="utf-8")
    assert pages._shell_partial("base.html") is None  # nothing else of the lifeboat's
    own = resources.files("egzos.authz").joinpath("templates")
    assert not own.joinpath("_shell.html").is_file()


@pytest.mark.parametrize("render", [pages.failure, pages.login, pages.device])
def test_every_page_is_signed_out_shell_with_no_script_and_one_stylesheet(render) -> None:
    page = render(**BOX)
    tags = Tags(page)
    assert not tags.find("script") and "style=" not in page and "<style" not in page
    assert tags.find("link", rel="stylesheet", href="/as.css")
    assert "egzos · container home · box.example:8443" in tags.text
    assert not tags.find("nav") and 'class="viewer"' not in page  # R1 signed-out
    assert len(tags.find("h1")) == 1 and tags.find("main")


@pytest.mark.parametrize("render", [pages.failure, pages.login, pages.device])
def test_data_from_outside_is_escaped(render) -> None:
    page = render(container="<script>x</script>", host='"><b>', stylesheet='/a.css"><x')
    assert "<script>" not in page and '"><b>' not in page and '"><x' not in page
    assert "&lt;script&gt;" in page


@pytest.mark.parametrize("field", ["container", "host", "stylesheet"])
def test_a_non_string_argument_is_refused(field: str) -> None:
    with pytest.raises(TypeError):
        pages.failure(**{**BOX, field: 1})


# --- §5.3: the uniform failure page -------------------------------------------------------------


def test_failure_is_400_with_one_copy_line_and_takes_no_cause() -> None:
    assert pages.FAILURE_STATUS == 400
    assert set(inspect.signature(pages.failure).parameters) == {"container", "host", "stylesheet"}
    page = pages.failure(**BOX)
    tags = Tags(page)
    assert tags.text == [
        "egzos",
        "egzos · container home · box.example:8443",
        "This request can't be completed.",
    ]
    assert not tags.find("form") and not tags.find("a") and not tags.find("input")
    assert pages.failure(**BOX) == page  # byte-identical however it is reached


# --- §11.7: /login ------------------------------------------------------------------------------


def test_login_ready() -> None:
    tags = Tags(pages.login(**BOX))
    assert tags.find("form", method="post", action=metadata.LOGIN_PATH)
    (secret,) = tags.find("input", id="secret")
    assert secret["type"] == "password" and secret["autocomplete"] == "current-password"
    assert secret["name"] == "secret" and "value" not in secret
    assert tags.find("label", **{"for": "secret"})
    assert "autofocus" in tags.find("h1")[0]  # R2: the heading takes first focus
    assert not tags.find("input", type="hidden")
    assert "Sign in to container home." in tags.text and "Sign in" in tags.text
    assert "That didn't work. Try again." not in tags.text


def test_login_failed_is_one_line_with_the_field_cleared_and_focused() -> None:
    tags = Tags(pages.login(**BOX, failed=True))
    (secret,) = tags.find("input", id="secret")
    assert "value" not in secret and "autofocus" in secret
    assert secret["aria-invalid"] == "true" and secret["aria-describedby"] == "login-error"
    assert tags.find("p", id="login-error", role="status")
    assert "That didn't work. Try again." in tags.text
    assert "autofocus" not in tags.find("h1")[0]


def test_login_failed_takes_only_true() -> None:
    assert pages.login(**BOX, failed="yes") == pages.login(**BOX)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "carry", ["/authorize?client_id=a&state=%2F%22x", "/device", "/pending/01J7", "/", "/?q=x"]
)
def test_login_carries_a_matched_continue_once_in_a_hidden_input(carry: str) -> None:
    assert continuation.resolve(carry) == carry
    page = pages.login(**BOX, carry=carry)
    tags = Tags(page)
    (hidden,) = tags.find("input", type="hidden")
    assert hidden == {"type": "hidden", "name": "continue", "value": carry}
    assert carry not in tags.text  # never rendered as content (§11.7)


def test_login_escapes_the_carry_for_its_attribute() -> None:
    carry = '/authorize?x="><script>alert(1)</script>'
    assert continuation.resolve(carry) == carry  # printable ASCII: D-C5 lets it through
    page = pages.login(**BOX, carry=carry)
    assert "<script>" not in page and '"><' not in page
    assert Tags(page).find("input", type="hidden")[0]["value"] == carry


@pytest.mark.parametrize(
    "carry",
    [
        "//evil.com/x",
        "/\\x",
        "/elsewhere",
        "/items/a/b",
        "/device?x=1",
        "/authorize#f",
        "",
        "https://evil.com/",
        "/" + "a" * 3000,
    ],
)
def test_login_refuses_to_carry_what_resolve_did_not_return(carry: str) -> None:
    assert continuation.resolve(carry) != carry
    with pytest.raises(ValueError):
        pages.login(**BOX, carry=carry)


# --- §11.8: /device -----------------------------------------------------------------------------


def test_device_ready() -> None:
    tags = Tags(pages.device(**BOX))
    assert tags.find("form", method="post", action=metadata.DEVICE_ENTRY_PATH)
    (code,) = tags.find("input", id="code")
    assert code == {
        "id": "code",
        "name": "user_code",
        "class": "code",
        "inputmode": "text",
        "autocomplete": "one-time-code",
        "spellcheck": "false",
        "maxlength": "9",
        "placeholder": "XXXX-XXXX",
    }
    assert "autofocus" in tags.find("h1")[0]
    assert tags.text[-1] == "Codes expire a few minutes after your terminal shows them."
    assert "That code isn't valid or has expired." not in tags.text


def test_device_takes_no_prefill() -> None:
    # [0.3 · 21]: a `user_code` query parameter has nowhere to go.
    assert set(inspect.signature(pages.device).parameters) == {
        "container",
        "host",
        "stylesheet",
        "failed",
        "entry",
    }
    assert pages.device(**BOX, entry="BCDF-GHJK") == pages.device(**BOX)


def test_device_failed_keeps_the_entry_and_says_one_line() -> None:
    tags = Tags(pages.device(**BOX, failed=True, entry="bcdf-ghjk"))
    (code,) = tags.find("input", id="code")
    assert code["value"] == "bcdf-ghjk" and "autofocus" in code
    assert code["aria-invalid"] == "true" and code["aria-describedby"] == "device-error"
    assert tags.find("p", id="device-error", role="status")
    assert "That code isn't valid or has expired." in tags.text


@pytest.mark.parametrize(
    ("entry", "kept"),
    [
        ('"><script>x', '"><script'),
        ("BCDF-GHJKLMNP", "BCDF-GHJK"),
        ("BC\x00DF\ud800GHéJK", "BCDFGHJK"),
        (None, ""),
        (12345678, ""),
    ],
)
def test_device_failed_entry_is_cut_and_escaped(entry: object, kept: str) -> None:
    page = pages.device(**BOX, failed=True, entry=entry)  # type: ignore[arg-type]
    page.encode("utf-8")  # nothing the caller sent can make the page unencodable
    assert "<script" not in page
    assert Tags(page).find("input", id="code")[0]["value"] == kept
