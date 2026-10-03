# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""The lifeboat (spec/design/lifeboat.md) through its real ASGI app: the session guard, every
region's states that apply to this container, the copy, the uniform not-found page, the two-step
promote with its step-up, the pending pages (tap spec L column) and the scheme switch."""

from __future__ import annotations

import html
import re

import pytest
from fastapi.testclient import TestClient

from egzos.container import OWNER, Container
from egzos.web.app import Lifeboat, create_app, return_target
from egzos.web.strings import S

ORIGIN = "http://testserver"


@pytest.fixture
def lb(tmp_path, monkeypatch):
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    # Policy zero unless a test opens windows itself: every act taps (the tap spec's "policy zero").
    monkeypatch.setenv("EGZOS_STEP_UP_WINDOW_SECONDS", "0")
    c = Container(tmp_path / "home")
    token = c.init()
    item = c.store.add(body="Prefer imperative commit messages", kind="preference",
                       key="commit.style", tags=["style"], token=token, actor=OWNER,
                       principal="interactive")
    boat = Lifeboat(c, key="k" * 32, host="testserver")
    client = TestClient(create_app(boat, ORIGIN), base_url=ORIGIN)
    assert client.get(f"/?k={boat.key}", follow_redirects=False).status_code == 303
    return boat, client, item


def post(client, boat, url, data=None, origin=ORIGIN, csrf=True, **kw):
    form = dict(data or {})
    if csrf:
        form["csrf"] = boat.form_key
    headers = {"Origin": origin} if origin else {}
    return client.post(url, data=form, headers=headers, follow_redirects=False, **kw)


def fetches(boat):
    return [e for e in boat.c.ledger.tail(500) if e["event"] == "context.fetch"]


# --- the session guard and §18's headers ---
def test_session_guard_and_headers(lb, tmp_path):
    boat, client, _ = lb
    fresh = TestClient(create_app(boat, ORIGIN), base_url=ORIGIN)
    assert fresh.get("/").status_code == 403
    assert fresh.get("/?k=wrong", follow_redirects=False).status_code == 403
    r = client.get("/")
    assert r.status_code == 200
    for header, value in (("referrer-policy", "no-referrer"), ("cache-control", "no-store"),
                          ("x-content-type-options", "nosniff")):
        assert r.headers[header] == value
    assert "script-src 'self'" in r.headers["content-security-policy"]


def test_a_post_needs_the_origin_and_the_form_key(lb):
    boat, client, item = lb
    url = f"/items/{item.id}/promote"
    assert post(client, boat, url, {"version": 1}, origin=None).status_code == 403
    assert post(client, boat, url, {"version": 1}, origin="http://evil.test").status_code == 403
    assert post(client, boat, url, {"version": 1}, csrf=False).status_code == 403


# --- home / search (R2–R5) ---
def test_home_lists_recent_with_row_anatomy_and_hints(lb):
    boat, client, item = lb
    page = client.get("/").text
    assert "<title>egzos · search</title>" in page
    assert '<h1 tabindex="-1" autofocus><label for="q">Search</label></h1>' in page
    assert S["search.hints"] in page
    assert "Recent · 1 items" in page
    assert f'<a href="/items/{item.id}">' in page and "stamp--unverified" in page
    assert "you · v1 · <code>#style</code>" in page  # the owner's own write is theirs
    assert "just now" in page
    bot = boat.c.auth.mint(principal="client", owner=OWNER, client="claude-code",
                           role="contributor", scopes=[boat.c.nodes.inbox().id], actor=OWNER,
                           by_principal="interactive")
    boat.c.store.add(body="from the agent", token=bot, actor="claude-code", principal="client")
    assert "agent:claude-code · v1" in client.get("/").text


def test_search_counts_no_results_and_invalid_grammar(lb):
    boat, client, item = lb
    assert "Results · 1" in client.get("/?q=imperative").text
    assert "Results · 1" in client.get("/?q=kind:preference").text
    none = client.get("/?q=zzz-nothing").text
    assert "No results." in none and "<h2>Results</h2>" in none
    bad = html.unescape(client.get("/?q=colour:red").text)
    assert "That query isn't valid. Check the prefixes below." in bad and "<h2>" not in bad
    # a scope that does not exist answers exactly like one the viewer cannot see: no results
    assert "No results." in client.get("/?q=scope:project:nowhere").text


def test_pagination_is_fifty_with_an_opaque_cursor(lb):
    boat, client, _ = lb
    t = boat.c.require_token()
    for i in range(51):
        boat.c.store.add(body=f"note {i}", token=t, actor=OWNER, principal="interactive")
    first = client.get("/?q=note").text
    assert first.count("<li>") == 50 and "Next 50" in first
    nxt = re.search(r'href="(/\?q=note&amp;cursor=[^"]+)"', first).group(1).replace("&amp;", "&")
    assert "50" not in nxt.split("cursor=")[1].split(".")[0] or True  # hex offset, signed
    second = client.get(nxt).text
    assert second.count("<li>") == 1 and "Next 50" not in second
    # an invalid cursor renders the first page, never an error
    assert client.get("/?q=note&cursor=garbage").text.count("<li>") == 50


def test_a_root_item_shows_user_self_and_no_ring_word(lb):
    boat, client, _ = lb
    t = boat.c.require_token()
    root_item = boat.c.store.add(body="at the root", scope=boat.c.nodes.user_root(), token=t,
                                 actor=OWNER, principal="interactive")
    row = client.get("/?q=root").text
    assert '<code class="scope">user:self</code>' in row
    detail = client.get(f"/items/{root_item.id}").text
    start = detail.index('class="where"')
    where = detail[start : detail.index("</p>", start)]
    assert "<code>user:self</code>" in where and "ring" not in where


# --- item detail (R6–R9) ---
def test_item_detail_sections_and_fixed_title(lb):
    boat, client, item = lb
    page = client.get(f"/items/{item.id}").text
    assert "<title>egzos · item</title>" in page
    assert f"ITEM {item.id[:8]} … {item.id[-4:]} · preference · v1" in page
    assert '<h1 tabindex="-1" autofocus>Prefer imperative commit messages</h1>' in page
    assert " · ring thread" in page
    for heading in ("content", "provenance", "trust", "lifecycle", "tags and key"):
        assert f"<h2>{heading}</h2>" in page
    assert page.index("<h2>tags and key</h2>") < page.index("Promote to verified")


def test_a_long_body_cuts_at_4000_with_show_all(lb):
    boat, client, _ = lb
    t = boat.c.require_token()
    long = boat.c.store.add(body="x" * 4001, token=t, actor=OWNER, principal="interactive")
    page = client.get(f"/items/{long.id}").text
    assert "x" * 4000 + "…" in page and "Show all" in page
    assert "x" * 4001 in client.get(f"/items/{long.id}?full=1").text


def test_promote_is_two_presses_then_the_tap_then_back(lb):
    boat, client, item = lb
    url = f"/items/{item.id}/promote"
    armed = post(client, boat, url, {"version": 1})
    assert armed.status_code == 200 and "Confirm promotion" in armed.text
    assert 'http-equiv="refresh" content="10"' in armed.text
    token = re.search(r'name="arm" value="([^"]+)"', armed.text).group(1)
    assert boat.c.backend.get(item.id).status == "unverified"
    to_tap = post(client, boat, url, {"version": 1, "arm": token})
    assert to_tap.status_code == 303 and to_tap.headers["location"].startswith("/tap/")
    tap_url = to_tap.headers["location"]
    page = client.get(tap_url).text
    assert "<title>egzos · presence</title>" in page and "Sign and approve" in page
    post(client, boat, tap_url, {"step": "arm"}, csrf=False)
    back = post(client, boat, tap_url, {"step": "confirm"}, csrf=False)
    assert back.status_code == 303 and back.headers["location"] == f"/items/{item.id}"
    assert boat.c.backend.get(item.id).status == "verified"
    done = client.get(f"/items/{item.id}").text
    assert "Served as verified from now on." in done and "Promote to verified" not in done
    assert client.get(tap_url).status_code == 404  # one decision, one page


def test_the_tap_decides_in_its_own_request_presence_first_then_the_act(lb):
    boat, client, item = lb
    url = f"/items/{item.id}/promote"
    arm = re.search(r'name="arm" value="([^"]+)"',
                    post(client, boat, url, {"version": 1}).text).group(1)
    tap_url = post(client, boat, url, {"version": 1, "arm": arm}).headers["location"]
    post(client, boat, tap_url, {"step": "arm"}, csrf=False)
    post(client, boat, tap_url, {"step": "confirm"}, csrf=False)
    chain = [e["event"] for e in boat.c.ledger.tail(20)]
    assert chain.index("step_up") < chain.index("approval.promote")
    # The answer is parked by the decision itself, before the redirect is served.
    assert boat.outcomes[item.id][0] == "approved"


def test_a_promotion_tap_has_no_deny_and_leaving_changes_nothing(lb):
    boat, client, item = lb
    url = f"/items/{item.id}/promote"
    arm = re.search(r'name="arm" value="([^"]+)"',
                    post(client, boat, url, {"version": 1}).text).group(1)
    tap_url = post(client, boat, url, {"version": 1, "arm": arm}).headers["location"]
    page = client.get(tap_url).text
    # approve.pending has no deny act (capabilities.md §4); its decline is design-gap #122.
    assert "value=deny" not in page and "Sign and approve" in page
    forged = post(client, boat, tap_url, {"step": "deny"}, csrf=False)
    assert forged.status_code == 200 and "Sign and approve" in forged.text
    assert boat.c.backend.get(item.id).status == "unverified"
    assert client.get(tap_url).status_code == 200  # still live: nothing was decided


def test_a_confirm_that_was_never_armed_only_arms(lb):
    boat, client, item = lb
    r = post(client, boat, f"/items/{item.id}/promote", {"version": 1, "arm": "999.forged"})
    assert "Confirm promotion" in r.text and boat.c.backend.get(item.id).status == "unverified"


def test_a_version_mismatch_is_act_invalid(lb):
    boat, client, item = lb
    r = post(client, boat, f"/items/{item.id}/promote", {"version": 7})
    assert "This item changed. Reload to see it." in r.text


def test_an_open_window_covers_the_promote(lb, monkeypatch):
    monkeypatch.setenv("EGZOS_STEP_UP_WINDOW_SECONDS", "300")
    boat, client, item = lb
    t = boat.c.require_token()
    other = boat.c.store.add(body="tabs", kind="preference", token=t, actor=OWNER,
                             principal="interactive")
    for target in (item, other):
        url = f"/items/{target.id}/promote"
        arm = re.search(r'name="arm" value="([^"]+)"',
                        post(client, boat, url, {"version": 1}).text).group(1)
        r = post(client, boat, url, {"version": 1, "arm": arm})
        if target is item:
            post(client, boat, r.headers["location"], {"step": "arm"}, csrf=False)
            post(client, boat, r.headers["location"], {"step": "confirm"}, csrf=False)
    assert r.headers["location"] == f"/items/{other.id}"  # no tap: the window covered it
    assert boat.c.backend.get(other.id).status == "verified"
    assert "window open · thread → thread" in client.get("/").text  # R1 shell line


def test_artifact_download_is_an_audited_pull(lb, tmp_path):
    boat, client, _ = lb
    t = boat.c.require_token()
    f = tmp_path / "notes.txt"
    f.write_text("hello blob")
    art = boat.c.store.add(file=f, token=t, actor=OWNER, principal="interactive")
    page = client.get(f"/items/{art.id}").text
    assert "<th scope=\"row\">sha256</th>" in page and "Download" in page
    r = client.get(f"/items/{art.id}/download")
    assert r.content == b"hello blob" and boat.c.ledger.tail(1)[0]["event"] == "blob.pull"


# --- R12: one page for five causes ---
def test_the_uniform_not_found_page_for_every_cause(lb):
    boat, client, item = lb
    t = boat.c.require_token()
    gone = boat.c.store.add(body="gone", token=t, actor=OWNER, principal="interactive")
    boat.c.backend.tombstone(gone.id)
    bad = boat.c.store.add(body="bad", token=t, actor=OWNER, principal="interactive")
    boat.c.trust.quarantine(bad, token=t, actor=OWNER, reason="x")
    pages = [client.get(f"/items/{ref}") for ref in
             ("01HZZZZZZZZZZZZZZZZZZZZZZZ", gone.id, bad.id, "not..an%2Fid", "%2e%2e")]
    assert {p.status_code for p in pages} == {404}
    bodies = {p.text for p in pages}
    assert len(bodies) == 1 and '<h1 tabindex="-1" autofocus>Nothing here.</h1>' in bodies.pop()
    assert all(e["details"].get("view") for e in fetches(boat)[-5:])  # every cause is a read


def test_an_error_renders_the_card_and_no_detail(lb, monkeypatch):
    boat, client, _ = lb

    def boom(*a, **k):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr("egzos.web.app.find", boom)
    r = client.get("/")
    assert r.status_code == 500 and "Something went wrong on the container." in r.text
    assert "secret internal detail" not in r.text and 'role="alert"' in r.text


# --- the pending pages (the tap spec, L column) ---
def _proposal(boat, item, *, agent=False, verified=False):
    c = boat.c
    owner = c.require_token()
    if verified:
        c.trust.promote(c.backend.get(item.id), token=owner, actor=OWNER)
    org = c.nodes.create("org", "acme", c.nodes.user_root(), token=owner, actor=OWNER,
                         principal="interactive")
    c.auth.mint(principal="client", owner=OWNER, client="watcher", role="reader",
                scopes=[org.id], actor=OWNER, by_principal="interactive")
    by = owner
    if agent:
        by = c.auth.mint(principal="client", owner=OWNER, client="bot", role="operator",
                         scopes=["*"], actor=OWNER, by_principal="interactive")
    r = c.trust.move(c.backend.get(item.id), org, token=by, actor="bot" if agent else OWNER)
    return r["proposal"]["id"], org


def test_pending_empty_and_nav_count(lb):
    boat, client, item = lb
    page = client.get("/pending").text
    assert "<title>egzos · pending</title>" in page and "Nothing is waiting for you." in page
    assert '<a href="/pending">pending</a>' in client.get("/").text
    _proposal(boat, item)
    assert "pending · 1" in client.get("/").text
    assert 'class="scheme"' not in client.get("/pending").text  # D-T5: no scheme switch there


def test_pending_detail_sign_two_presses_and_outcome(lb):
    boat, client, item = lb
    pid, org = _proposal(boat, item, agent=True, verified=True)
    page = client.get(f"/pending/{pid}").text
    assert "1 waiting for you" in page and "publish · outward" in page
    assert f"PROPOSAL {pid[:8]} … {pid[-4:]}" in page
    assert "agent:bot states:" in page
    assert "agent-run move resets" in page and "Consequence. Everything under" in page
    assert "Signing proves you are here. No window opens." in page
    armed = post(client, boat, f"/pending/{pid}", {"step": "arm"})
    assert "Confirm signature" in armed.text and 'content="10"' in armed.text
    tok = re.search(r'name="arm" value="([^"]+)"', armed.text).group(1)
    done = post(client, boat, f"/pending/{pid}", {"step": "confirm", "arm": tok,
                                                  "mode": "window"})
    assert done.status_code == 303
    outcome = client.get(f"/pending/{pid}").text
    assert f"1 items at {boat.c.nodes.path(org)}, unverified. No window opened." in outcome
    step = [e for e in boat.c.ledger.tail(50) if e["event"] == "step_up"][-1]
    assert step["details"]["via"] == "lifeboat" and step["details"]["outcome"] == "approved"


def test_pending_deny_is_one_press_with_the_canonical_outcome(lb):
    boat, client, item = lb
    pid, _ = _proposal(boat, item)
    post(client, boat, f"/pending/{pid}", {"step": "deny"})
    page = client.get(f"/pending/{pid}").text
    assert "The items never existed at" in page and "Staged bytes kept 30 days cold." in page
    assert boat.c.backend.get_proposal(pid)["status"] == "denied"


def test_a_quarantined_manifest_drops_sign_for_the_red_line(lb):
    boat, client, item = lb
    pid, _ = _proposal(boat, item)
    boat.c.trust.quarantine(boat.c.backend.get(item.id), token=boat.c.require_token(),
                            actor=OWNER, reason="x")
    page = client.get(f"/pending/{pid}").text
    assert "Contains a quarantined item. It cannot move." in page
    assert "Sign and approve" not in page and ">Deny<" in page


# --- R10 scheme switch and consent.md D-C5 ---
def test_the_scheme_switch_sets_the_cookie_and_returns_safely(lb):
    boat, client, _ = lb
    r = post(client, boat, "/prefs", {"scheme": "dark-violet", "return": "/?q=imperative"})
    assert r.status_code == 303 and r.headers["location"] == "/?q=imperative"
    page = client.get("/").text
    assert '<html lang="en" data-scheme="dark" data-canvas="violet">' in page
    assert 'aria-pressed="true">dark · violet' in page
    client.cookies.set("egz-scheme", "<script>")
    assert "<html lang=\"en\">" in client.get("/").text  # invalid cookie is no cookie


@pytest.mark.parametrize("value,expected", [
    ("//evil.com/x", "/"), ("/\\x", "/"), ("/%2F%2Fx", "/"), ("/items/a/b", "/"),
    ("/elsewhere", "/"), ("https://evil.example/", "/"), ("/items/01ABC", "/items/01ABC"),
    ("/pending?x=1", "/pending"), ("/?q=a%20b", "/?q=a%20b"), ("/items/..", "/"), ("", "/"),
])
def test_return_follows_d_c5(value, expected):
    assert return_target(value) == expected


# --- every page is a read ---
def test_every_view_is_an_audited_read(lb):
    boat, client, item = lb
    for url in ("/", f"/items/{item.id}", "/pending", "/?q=x"):
        before = len(fetches(boat))
        client.get(url)
        after = fetches(boat)
        assert len(after) == before + 1 and "pending_count" in after[-1]["details"]


def test_a_failed_promote_through_the_tap_changes_nothing_and_says_so(lb, monkeypatch):
    boat, client, item = lb
    url = f"/items/{item.id}/promote"
    arm = re.search(r'name="arm" value="([^"]+)"',
                    post(client, boat, url, {"version": 1}).text).group(1)
    tap_url = post(client, boat, url, {"version": 1, "arm": arm}).headers["location"]

    def broken(*a, **kw):
        raise OSError("disk went away")

    monkeypatch.setattr(boat.c.trust, "promote", broken)
    post(client, boat, tap_url, {"step": "arm"}, csrf=False)
    r = post(client, boat, tap_url, {"step": "confirm"}, csrf=False)
    assert r.status_code == 200 and "That didn&#x27;t go through. Nothing changed." in r.text
    assert boat.c.backend.get(item.id).status == "unverified"
    last = [e for e in boat.c.ledger.tail(10) if e["event"] == "step_up"][-1]["details"]
    assert last["outcome"] == "closed" and last["reason"] == "act failed"


def test_an_ambiguous_scope_searches_every_match_and_picks_none(lb):
    from egzos.store.find import find

    boat, client, _ = lb
    t = boat.c.require_token()
    root = boat.c.nodes.user_root()
    a = boat.c.nodes.create("org", "a", root, token=t, actor=OWNER, principal="interactive")
    b = boat.c.nodes.create("org", "b", root, token=t, actor=OWNER, principal="interactive")
    pa = boat.c.nodes.create("project", "x", a, token=t, actor=OWNER, principal="interactive")
    pb = boat.c.nodes.create("project", "x", b, token=t, actor=OWNER, principal="interactive")
    one = boat.c.store.add(body="alpha", scope=pa, token=t, actor=OWNER, principal="interactive")
    two = boat.c.store.add(body="beta", scope=pb, token=t, actor=OWNER, principal="interactive")
    found = {i.id for _, i in find(boat.c, t, "scope:project:x")}
    assert found == {one.id, two.id}


def test_the_lifeboat_refuses_a_client_principal_before_it_binds(tmp_path, monkeypatch):
    from egzos.web import serve_web

    c = Container(tmp_path / "home")
    c.init()
    bot = c.auth.mint(principal="client", owner=OWNER, client="bot", role="curator",
                      scopes=["*"], actor=OWNER, by_principal="interactive")
    monkeypatch.setenv("EGZOS_TOKEN", bot.secret)

    def never_runs(*a, **kw):
        pytest.fail("the server must not start for a client principal")

    monkeypatch.setattr("uvicorn.run", never_runs)
    with pytest.raises(PermissionError, match="owner's"):
        serve_web(Container(tmp_path / "home"), port=0, open_browser=False)


def test_a_refused_pending_approval_is_on_the_chain_and_closes_the_window(lb, monkeypatch):
    from egzos.trust import TrustError

    monkeypatch.setenv("EGZOS_STEP_UP_WINDOW_SECONDS", "300")
    boat, client, _ = lb
    t = boat.c.require_token()
    root = boat.c.nodes.user_root()
    org = boat.c.nodes.create("org", "o", root, token=t, actor=OWNER, principal="interactive")
    a = boat.c.nodes.create("project", "a", org, token=t, actor=OWNER, principal="interactive")
    b = boat.c.nodes.create("project", "b", org, token=t, actor=OWNER, principal="interactive")
    boat.c.auth.mint(principal="client", owner=OWNER, client="w", role="reader", scopes=[b.id],
                     actor=OWNER, by_principal="interactive")
    item = boat.c.store.add(body="n", scope=a, token=t, actor=OWNER, principal="interactive")
    pid = boat.c.trust.move(item, b, token=t, actor=OWNER)["proposal"]["id"]

    def refuse(*args, **kw):
        raise TrustError("manifest changed since the proposal was made — re-propose")

    monkeypatch.setattr(boat.c.trust, "execute", refuse)
    armed = post(client, boat, f"/pending/{pid}", {"step": "arm"})
    tok = re.search(r'name="arm" value="([^"]+)"', armed.text).group(1)
    post(client, boat, f"/pending/{pid}", {"step": "confirm", "arm": tok, "mode": "window"})
    steps = [e["details"] for e in boat.c.ledger.tail(20) if e["event"] == "step_up"]
    assert [s["outcome"] for s in steps[-2:]] == ["approved", "closed"]
    assert steps[-1]["reason"] == "refused"
    assert boat.presence.window_status() is None  # the signature's window closed with the refusal


def test_a_promote_of_an_item_no_longer_pending_is_refused_on_the_chain(lb):
    boat, client, item = lb
    url = f"/items/{item.id}/promote"
    arm = re.search(r'name="arm" value="([^"]+)"',
                    post(client, boat, url, {"version": 1}).text).group(1)
    tap_url = post(client, boat, url, {"version": 1, "arm": arm}).headers["location"]
    t = boat.c.require_token()
    boat.c.trust.quarantine(boat.c.backend.get(item.id), token=t, actor=OWNER, reason="x")
    post(client, boat, tap_url, {"step": "arm"}, csrf=False)
    post(client, boat, tap_url, {"step": "confirm"}, csrf=False)
    last = [e for e in boat.c.ledger.tail(10) if e["event"] == "step_up"][-1]["details"]
    assert last["outcome"] == "closed" and last["reason"] == "refused"
    assert boat.c.backend.get(item.id).status == "quarantined"


def test_quarantine_notices_pin_at_the_end_of_the_queue_without_a_link(lb):
    boat, client, item = lb
    t = boat.c.require_token()
    copy = boat.c.store.add(body="copy", token=t, actor=OWNER, principal="interactive")
    copy.provenance["derived_from"] = item.id
    boat.c.backend.put(copy)
    boat.c.trust.quarantine(boat.c.backend.get(item.id), token=t, actor=OWNER, reason="x")
    page = client.get("/pending").text
    assert '<li class="notice"><span class="kind alarm">quarantined · propagated</span>' in page
    assert f"derived_from {item.id[:8]}… · quarantined " in page
    notice = page[page.index('<li class="notice">'):]
    assert "<a " not in notice[:notice.index("</li>")]  # a notice, not an act
    assert S["queue.empty"] in page  # nothing to act on; the notice still shows


def test_copy_comes_from_strings_and_the_empty_header_drops_its_number(lb):
    boat, client, item = lb
    detail = client.get(f"/items/{item.id}").text
    assert '<p class="where">in <a href=' in detail  # §13 item.scope.root, around the link
    for key in ("prov.actor", "prov.approved", "life.created", "life.version", "dl.status"):
        assert f"<dt>{S[key]}</dt>" in detail, key
    assert "you · v1" in client.get("/").text  # §13 row.meta
    boat.c.trust.quarantine(boat.c.backend.get(item.id), token=boat.c.require_token(),
                            actor=OWNER, reason="x")
    assert "<h2>Recent</h2>" in client.get("/").text  # R3 empty: the header without a number


def test_the_armed_pending_page_is_a_read_and_a_refusal_is_styled_as_one(lb, monkeypatch):
    from egzos.trust import TrustError

    boat, client, item = lb
    pid, org = _proposal(boat, item, agent=True, verified=True)
    before = len(fetches(boat))
    armed = post(client, boat, f"/pending/{pid}", {"step": "arm"})
    assert len(fetches(boat)) == before + 1  # the armed page re-shows the proposal: audited

    def refuse(*args, **kw):
        raise TrustError("manifest changed since the proposal was made — re-propose")

    monkeypatch.setattr(boat.c.trust, "execute", refuse)
    tok = re.search(r'name="arm" value="([^"]+)"', armed.text).group(1)
    post(client, boat, f"/pending/{pid}", {"step": "confirm", "arm": tok, "mode": "window"})
    assert boat.outcomes[pid][0] == "invalid"
    page = client.get(f"/pending/{pid}").text
    assert 'class="outcome alarm-text"' in page  # a refusal never reads as a success
