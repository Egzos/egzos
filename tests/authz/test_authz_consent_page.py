# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The consent screen (authz/pages.py `consent`; consent.md §2.3, R4 to R11; contract §11.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from egzos._types import AS_GRANT_LIFETIME_MAX_SECONDS, CAPABILITIES
from egzos.authz import metadata, pages, presence
from egzos.authz.grant import Offer, offer
from egzos.authz.screen import ClientEntry, ExistingTokens
from tests.authz.test_authz_pages import Tags

AT = datetime(2026, 10, 13, 21, 31, 4, tzinfo=UTC)
WEB = ClientEntry(
    "web_01J7ABCDEFGH9KQ2", "Claude", "browser", ("https://claude.ai/cb",), "2026-09-21T10:00:00Z"
)
MCP = ClientEntry(
    "mcp_01J7X", "Agent", "mcp", ("https://agent.example/cb",), "2026-09-21T10:00:00Z"
)
CLI = ClientEntry("cli_01J7Y", "Terminal", "cli", (), "2026-09-21T10:00:00Z")
ATLAS = {"n1": pages.ScopeLabel("project", "atlas")}
ARM = "a" * 32


def render(**over: Any) -> str:
    args: dict[str, Any] = {
        "container": "home",
        "host": "box.example:8443",
        "stylesheet": "/as.css",
        "viewer": "ali",
        "signed_in": AT - timedelta(minutes=5),
        "at": AT,
        "client": MCP,
        "offer": offer("fetch node:n1", client_type="mcp", lifetime_seconds=None),
        "labels": ATLAS,
        "existing": ExistingTokens(0, None),
        "fields": {"request": "r1", "csrf": "c1"},
        "redirect_uri": "https://agent.example/cb",
    }
    args.update(over)
    return pages.consent(**args)


def acts(page: str) -> list[dict[str, str | None]]:
    return Tags(page).find("button")


# --- R4 to R10: what renders is the offer ---------------------------------------------------------


def test_ready_narrow_grant_is_one_press_with_the_offer_and_nothing_else() -> None:
    page = render()
    tags = Tags(page)
    assert "egzos · grant request" in tags.text
    assert "you · ali · principal: interactive · signed in 21:26" in tags.text
    assert "GRANT REQUEST · Agent · requested 21:31:04" in tags.text
    assert "Agent asks for a token to your container." in tags.text
    assert "autofocus" in tags.find("h1")[0] and not any("autofocus" in b for b in acts(page))
    solid = [a for a in tags.find("li") if a.get("class") == "stamp stamp--solid"]
    assert len(solid) == 1 and len(tags.find("li", **{"aria-description": "requested"})) == 1
    # Six stamps in ladder order, then one line per requested capability.
    assert [t for t in tags.text if t in CAPABILITIES] == [*CAPABILITIES, "fetch"]
    assert "— reading context; downloading artifacts is fetch" in tags.text
    assert "role · reader" in tags.text
    assert "project:atlas · ring project" in tags.text
    coverage = pages.COPY["scope.coverage"].format(scope="project:atlas")
    assert coverage.startswith("Coverage reaches everything under project:atlas — ")
    assert coverage in tags.text
    assert pages.COPY["principal.client"] in tags.text
    assert "expires 2026-11-12 21:31:04 · in 30 d" in tags.text  # §11.5's default, from `at`
    assert tags.find("time", datetime=(AT + timedelta(days=30)).isoformat())
    assert [(b["name"], b["value"]) for b in acts(page)] == [
        ("step", "authorize"),
        ("step", "deny"),
    ]
    assert pages.COPY["wide.note"] not in tags.text
    assert tags.find("form", method="post", action=metadata.AUTHORIZE_PATH)
    hidden = {a["name"]: a["value"] for a in tags.find("input", type="hidden")}
    assert hidden == {"csrf": "c1", "request": "r1"}
    assert "redirects to https://agent.example" in tags.text and "mcp" in tags.text
    assert "registered 2026-09-21" in tags.text
    hint = pages.COPY["narrow.hint"].removesuffix("egzos token mint")
    assert f'<p class="hint">{hint}<code>egzos token mint</code></p>' in page
    assert not tags.find("script") and "style=" not in page and not tags.find("nav")
    assert tags.find("div", **{"class": "frame frame--consent"})


def test_a_browser_grant_is_interactive_so_wide_and_two_step() -> None:
    o = offer("fetch node:n1", client_type="browser", lifetime_seconds=None)
    page = render(client=WEB, offer=o, redirect_uri="https://claude.ai/cb")
    tags = Tags(page)
    assert tags.find("p", **{"class": "box principal", "role": "note"})
    assert pages.COPY["principal.interactive"] in tags.text
    assert tags.find("p", id="wide-note")
    first = acts(page)[0]
    assert (first["value"], first["aria-describedby"]) == ("arm", "wide-note")
    assert "Authorize" in tags.text and "Confirm authorization" not in tags.text


def test_armed_wide_grant_confirms_with_the_arm_token() -> None:
    o = offer("curate node:n1", client_type="mcp", lifetime_seconds=None)
    page = render(offer=o, arm=ARM)
    tags = Tags(page)
    assert acts(page)[0]["value"] == "confirm" and "Confirm authorization" in tags.text
    assert tags.find("input", type="hidden", name="arm", value=ARM)
    assert "Press again to confirm." in tags.text
    assert tags.find("section", **{"class": "framed"})  # R7: curate frames the block


def test_a_narrow_grant_never_arms() -> None:
    with pytest.raises(ValueError):
        render(arm=ARM)


@pytest.mark.parametrize("arm", ["short", "x" * 16 + "<", 12345678901234567890])
def test_an_arm_token_in_a_bad_shape_is_refused(arm: object) -> None:
    wide = offer("admin node:n1", client_type="mcp", lifetime_seconds=None)
    with pytest.raises(ValueError):
        render(offer=wide, arm=arm)


def test_all_six_is_role_admin() -> None:
    o = offer(" ".join(CAPABILITIES) + " node:n1", client_type="mcp", lifetime_seconds=None)
    tags = Tags(render(offer=o))
    assert "role · admin" in tags.text
    assert len(tags.find("li", **{"aria-description": "requested"})) == 6


def test_a_set_that_is_no_bundle_is_a_custom_set() -> None:
    o = offer("fetch publish node:n1", client_type="mcp", lifetime_seconds=None)
    assert "custom set" in Tags(render(offer=o)).text


def test_whole_container_is_wide_with_its_consequence_box() -> None:
    o = offer("fetch node:*", client_type="mcp", lifetime_seconds=None)
    page = render(offer=o, labels={})
    tags = Tags(page)
    assert "whole container" in tags.text and pages.COPY["scope.all"] in tags.text
    assert acts(page)[0]["value"] == "arm"


@pytest.mark.parametrize(
    ("ring", "flagged", "wide"),
    [
        ("project", False, False),
        ("org", True, True),
        ("global", True, True),
        ("user", False, True),
        ("moon", False, True),
    ],
)
def test_d_c1_scope_rows(ring: str, flagged: bool, wide: bool) -> None:
    label = pages.ScopeLabel(ring, "x")
    assert (label.flagged, label.wide) == (flagged, wide)
    page = render(labels={"n1": label})
    assert (acts(page)[0]["value"] == "arm") is wide
    assert f"{ring}:x · ring {ring}" in Tags(page).text  # an unknown ring renders verbatim
    assert bool(Tags(page).find("code", **{"aria-description": "wide scope"})) is flagged


def test_org_or_wider_sorts_first() -> None:
    o = offer("fetch node:a node:b", client_type="mcp", lifetime_seconds=None)
    labels = {"a": pages.ScopeLabel("project", "p"), "b": pages.ScopeLabel("org", "o")}
    lines = [t for t in Tags(render(offer=o, labels=labels)).text if " · ring " in t]
    assert lines == ["org:o · ring org", "project:p · ring project"]


def test_more_than_eight_scopes_is_partial_only_with_the_more_address() -> None:
    ids = [f"n{i}" for i in range(9)]
    o = offer(
        "fetch " + " ".join(f"node:{i}" for i in ids), client_type="mcp", lifetime_seconds=None
    )
    labels = {i: pages.ScopeLabel("project", i) for i in ids}
    more = "/authorize?client_id=mcp&full=1"
    tags = Tags(render(offer=o, labels=labels, more=more))
    assert sum(" · ring " in t for t in tags.text) == 8
    assert tags.find("a", href=more) and "+ 1 more" in tags.text
    every = Tags(render(offer=o, labels=labels))
    assert sum(" · ring " in t for t in every.text) == 9 and not every.find("a")
    with pytest.raises(ValueError):
        render(offer=o, labels=labels, more="//evil.example/x")


def test_a_clamped_expiry_renders_clamped() -> None:
    o = offer("fetch node:n1", client_type="mcp", lifetime_seconds=10**9)
    tags = Tags(render(offer=o, requested_lifetime_seconds=10**9))
    assert "shortened to the container's maximum" in tags.text
    days = AS_GRANT_LIFETIME_MAX_SECONDS // 86400
    assert any(t.endswith(f"· in {days} d") for t in tags.text)
    assert "shortened to the container's maximum" not in Tags(render()).text


@pytest.mark.parametrize(
    ("seconds", "left"), [(86400 * 2 + 5, "2 d"), (3600 * 5, "5 h"), (180, "3 min"), (30, "1 min")]
)
def test_expiry_counts_down_in_the_s5_units(seconds: int, left: str) -> None:
    o = Offer(("fetch",), ("n1",), "client", seconds)
    assert any(t.endswith(f"· in {left}") for t in Tags(render(offer=o)).text)


def test_existing_tokens_line() -> None:
    line = (
        "This client already holds 2 live tokens · latest minted 2026-10-01. "
        "Authorizing mints another."
    )
    assert line in Tags(render(existing=ExistingTokens(2, "2026-10-01T08:00:00Z"))).text
    assert not any("already holds" in t for t in Tags(render()).text)
    dashed = Tags(render(existing=ExistingTokens(1, None))).text
    assert any("latest minted —." in t for t in dashed)


def test_dates_and_times_render_in_the_zone_of_at() -> None:
    at = AT.astimezone(timezone(timedelta(hours=-7)))
    tags = Tags(render(at=at, signed_in=at, client=MCP))
    assert "GRANT REQUEST · Agent · requested 14:31:04" in tags.text
    assert "registered 2026-09-21" in tags.text


# --- R5: the client block -------------------------------------------------------------------------


def test_device_variant_shows_the_code_and_no_redirect() -> None:
    o = offer("fetch node:n1", client_type="cli", lifetime_seconds=None)
    tags = Tags(render(client=CLI, offer=o, redirect_uri=None, user_code="BCDF-GHJK"))
    assert "GRANT REQUEST · Terminal · requested 21:31:04 · code BCDF-GHJK" in tags.text
    assert "device" in tags.text and not any(t.startswith("redirects to") for t in tags.text)
    with pytest.raises(ValueError):
        render(client=CLI, offer=o, redirect_uri=None)
    with pytest.raises(ValueError):
        render(client=CLI, offer=o, redirect_uri="https://x/cb", user_code="BCDF-GHJK")


@pytest.mark.parametrize(
    ("uri", "line"),
    [
        (
            "http://127.0.0.1:8731/cb",
            "redirects to http://127.0.0.1:8731 · local development origin",
        ),
        ("http://[::1]:5173/cb", "redirects to http://[::1]:5173 · local development origin"),
    ],
)
def test_a_loopback_redirect_is_a_local_development_origin(uri: str, line: str) -> None:
    client = ClientEntry(
        "mcp_l", "Dev", "mcp", (uri.replace(":8731", "").replace(":5173", ""),), "2026-09-21"
    )
    assert line in Tags(render(client=client, redirect_uri=uri)).text


@pytest.mark.parametrize(
    "uri", ["https://agent.example/cb/x", "https://agent.example/", None, "https://evil.example/cb"]
)
def test_a_redirecting_client_needs_its_registered_redirect(uri: str | None) -> None:
    with pytest.raises(ValueError):
        render(redirect_uri=uri)
    with pytest.raises(ValueError):
        render(user_code="BCDF-GHJK")


def test_a_long_name_is_cut_with_the_whole_name_in_title_and_the_id_shortened() -> None:
    name = "N" * 70
    client = ClientEntry("mcp_01J7ABCDEFGH9KQ2", name, "mcp", MCP.redirect_uris, "2026-09-21")
    tags = Tags(render(client=client))
    assert f"{'N' * 64}… asks for a token to your container." in tags.text
    assert tags.find("h1")[0]["title"] == name
    assert tags.find("code", title="mcp_01J7ABCDEFGH9KQ2") and "mcp_01J7 … 9KQ2" in tags.text


# --- R4 invalid, R11 error ------------------------------------------------------------------------


def test_invalid_has_the_line_the_headings_and_no_acts() -> None:
    tags = Tags(render(invalid=True))
    assert "This request is no longer valid." in tags.text
    assert not tags.find("form") and not tags.find("button")
    assert [t for t in tags.text if t in ("capabilities", "scopes", "expiry")] == [
        "capabilities",
        "scopes",
        "expiry",
    ]
    assert not any(" · ring " in t for t in tags.text)


def test_mint_failed_keeps_the_acts_with_one_red_line() -> None:
    page = render(failed=True)
    assert Tags(page).find("p", **{"class": "alarm", "role": "status"})
    assert pages.COPY["act.error"] in Tags(page).text and len(acts(page)) == 2
    assert pages.COPY["act.error"] not in Tags(render(failed="yes")).text


# --- refusals -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("over", "error"),
    [
        ({"at": datetime(2026, 10, 13)}, TypeError),
        ({"signed_in": "21:00"}, TypeError),
        ({"client": object()}, TypeError),
        ({"offer": "fetch"}, TypeError),
        ({"viewer": None}, TypeError),
        ({"existing": (0, None)}, TypeError),
        ({"labels": {}}, ValueError),
        ({"fields": {"step": "x"}}, ValueError),
        ({"fields": {"Request": "x"}}, ValueError),
        ({"fields": {"request": 1}}, TypeError),
        (
            {"client": ClientEntry("mcp_01J7X", "Agent", "mcp", MCP.redirect_uris, "soon")},
            ValueError,
        ),
    ],
)
def test_misuse_is_refused(over: dict[str, Any], error: type[Exception]) -> None:
    with pytest.raises(error):
        render(**over)


def test_a_scope_label_is_two_strings() -> None:
    with pytest.raises(TypeError):
        pages.ScopeLabel("project", None)  # type: ignore[arg-type]


def test_data_from_outside_is_escaped() -> None:
    client = ClientEntry("mcp_01J7X", "<script>x</script>", "mcp", MCP.redirect_uris, "2026-09-21")
    page = render(
        client=client,
        viewer='"><b>',
        labels={"n1": pages.ScopeLabel("project", "<img src=x>")},
        fields={"request": '"><i>'},
    )
    assert (
        "<script>" not in page
        and "<img" not in page
        and '"><b>' not in page
        and '"><i>' not in page
    )
    assert "&lt;script&gt;" in page


def test_the_stylesheet_head_is_presences_public_tokens_css() -> None:
    assert pages.css() == presence.tokens_css() + pages.STYLE
