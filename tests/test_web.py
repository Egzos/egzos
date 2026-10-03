# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""The lifeboat (MVP cut): views, acts, and the loopback session guard."""

from __future__ import annotations

import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from urllib.parse import urlencode

import pytest

from egzos.container import OWNER, Container
from egzos.web import Lifeboat, _launch, make_handler


@pytest.fixture
def boat(tmp_path):
    c = Container(tmp_path)
    token = c.init()
    item = c.store.add(
        body="Prefer imperative commit messages",
        file=None,
        kind="preference",
        scope=None,
        key="commit.style",
        tags=[],
        token=token,
        actor=OWNER,
        principal=token.principal,
    )
    return Lifeboat(c, key="k" * 32), item


def test_items_lists_and_searches(boat):
    b, item = boat
    status, body = b.items()
    assert status == 200 and "Prefer imperative commit messages" in body
    status, body = b.items("nothing-matches-this")
    assert "No matches." in body
    assert b.c.ledger.tail(1)[0]["event"] == "context.fetch"


def test_item_detail_escapes_and_unknown_is_uniform(boat):
    b, item = boat
    item.content["body"] = "<script>alert(1)</script>"
    b.c.backend.put(item)
    status, body = b.item(item.id)
    assert status == 200
    assert "<script>alert(1)</script>" not in body and "&lt;script&gt;" in body
    assert b.item("01UNKNOWN")[0] == 404


def _step_ups(c):
    return [e["details"] for e in c.ledger.tail(200) if e["event"] == "step_up"]


def _to_tap(b, ref, back="/pending"):
    _, _, redirect = b.act("/approve", {"ref": ref, "back": back})
    assert redirect.startswith("/tap/")
    return redirect[len("/tap/") :]


def test_approve_redirects_to_the_tap_which_needs_two_presses(boat, monkeypatch):
    monkeypatch.setenv("EGZOS_STEP_UP_WINDOW_SECONDS", "300")
    b, item = boat
    # The lifeboat's Approve never performs: it hands the decision to a one-shot tap page.
    token = _to_tap(b, item.id)
    assert b.c.backend.get(item.id).status == "unverified"
    status, page = b.tap_get(token)
    for required in ("egzos · container", "principal: interactive", "what moves",
                     "who will see it at", "presence", "Sign and approve", "window would close"):
        assert required in page, required
    b.tap_post(token, "confirm")  # a confirm with no arm signs nothing
    assert b.c.backend.get(item.id).status == "unverified"
    assert "Confirm signature" in b.tap_post(token, "arm")[1]
    status, outcome = b.tap_post(token, "confirm")
    assert "Signed at" in outcome and 'href="/pending"' in outcome
    assert b.c.backend.get(item.id).status == "verified"
    assert b.c.ledger.tail(1)[0]["event"] == "approval.promote"
    signed = _step_ups(b.c)[-1]
    assert signed["via"] == "tap" and signed["outcome"] == "approved"
    assert signed["shape"] == {"max_items": 1, "kinds": ["preference"]}
    assert b.tap_get(token)[0] == 404 and b.c.ledger.verify()["ok"]  # one decision, one page


def test_a_window_covers_only_what_fits_the_signed_shape(boat, monkeypatch):
    monkeypatch.setenv("EGZOS_STEP_UP_WINDOW_SECONDS", "300")
    b, item = boat
    token = b.c.require_token()
    same = b.c.store.add(body="tabs", kind="preference", token=token, actor=OWNER,
                         principal=token.principal)
    other = b.c.store.add(body="a memory", token=token, actor=OWNER, principal=token.principal)
    t = _to_tap(b, item.id)
    b.tap_post(t, "arm")
    b.tap_post(t, "confirm")
    # same ring pair (thread → thread), same shape: one press, logged as a window pass
    _, _, redirect = b.act("/approve", {"ref": same.id, "back": "/pending"})
    assert redirect.startswith("/pending?ok=") and b.c.backend.get(same.id).status == "verified"
    assert _step_ups(b.c)[-1]["outcome"] == "window"
    # a different kind is outside the signed shape: back to the tap
    assert _to_tap(b, other.id) and b.c.backend.get(other.id).status == "unverified"


def test_an_undecided_tap_expires_on_the_record(boat, monkeypatch):
    b, item = boat
    token = _to_tap(b, item.id)
    monkeypatch.setenv("EGZOS_TAP_TIMEOUT_SECONDS", "0.001")
    import time

    time.sleep(0.01)
    assert b.tap_get(token)[0] == 404
    assert _step_ups(b.c)[-1]["outcome"] == "expired"


def test_back_is_kept_on_this_origin(boat):
    b, item = boat
    for back in ("https://evil.test/", "//evil.test/x"):
        token = _to_tap(b, item.id, back=back)
        assert b.taps[token]["back"] == "/pending"


def test_proposal_approve_and_deny(boat):
    b, item = boat
    c = b.c
    token = c.require_token()
    org = c.nodes.create(
        "org", "acme", c.nodes.user_root(), token=token, actor=OWNER, principal="interactive"
    )
    c.auth.mint(principal="client", owner=OWNER, client="ops", role="operator",
                scopes=[org.id], actor=OWNER, by_principal="interactive")
    r = c.trust.move(item, org, token=token, actor=OWNER)
    pid = r["proposal"]["id"]
    assert "Approve this move" in b.pending()[1]
    page = b.tap_get(_to_tap(b, pid))[1]
    assert "Consequence. Everything under" in page and "1 people · 1 agents" in page
    _, _, redirect = b.act("/deny", {"proposal": pid, "back": "/pending"})
    assert "Denied" in redirect.replace("+", " ")
    assert c.ledger.tail(1)[0]["event"] == "approval.deny"
    assert _step_ups(c)[-1]["outcome"] == "denied" and _step_ups(c)[-1]["pair"] == ["thread", "org"]


def test_every_view_is_a_read_with_the_pending_count(boat):
    b, item = boat
    for view in (lambda: b.items(), lambda: b.pending(), lambda: b.item(item.id)):
        view()
        e = b.c.ledger.tail(1)[0]
        assert e["event"] == "context.fetch" and e["details"]["pending_count"] == 1


def _serve(tmp_path, ready, holder):
    # The container's sqlite handle belongs to the thread that opens it, so the server thread
    # builds its own container, as `egzos web` does in its single thread.
    c = Container(tmp_path)
    c.init()
    boat = Lifeboat(c, key="secret-key-for-tests")
    httpd = HTTPServer(("127.0.0.1", 0), make_handler(boat, "http://127.0.0.1"))
    holder["port"] = httpd.server_address[1]
    holder["httpd"] = httpd
    ready.set()
    httpd.serve_forever()


@pytest.fixture
def server(tmp_path):
    ready, holder = threading.Event(), {}
    t = threading.Thread(target=_serve, args=(tmp_path, ready, holder), daemon=True)
    t.start()
    ready.wait(5)
    yield holder["port"]
    holder["httpd"].shutdown()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _open(url, data=None, headers=None):
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        r = opener.open(req)
        return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def test_session_guard(server):
    base = f"http://127.0.0.1:{server}"
    assert _open(base + "/")[0] == 403
    assert _open(base + "/?k=wrong")[0] == 404
    status, headers, _ = _open(base + "/?k=secret-key-for-tests")
    assert status == 303
    cookie = headers["Set-Cookie"].split(";")[0]
    assert "HttpOnly" in headers["Set-Cookie"] and "SameSite=Strict" in headers["Set-Cookie"]
    assert _open(base + "/", headers={"Cookie": cookie})[0] == 200
    assert _open(base + "/static/tokens.css", headers={"Cookie": cookie})[0] == 200
    form = urlencode({"ref": "x", "back": "/pending"}).encode()
    # A POST without the form key, or from another origin, is refused.
    assert _open(base + "/approve", form, {"Cookie": cookie})[0] == 403
    form_k = urlencode({"ref": "x", "csrf": "secret-key-for-tests"}).encode()
    evil = {"Cookie": cookie, "Origin": "http://evil.test"}
    assert _open(base + "/approve", form_k, evil)[0] == 403
    # A missing Origin is refused as well; only this origin reaches the act (here: no such ref).
    assert _open(base + "/approve", form_k, {"Cookie": cookie})[0] == 403
    same = {"Cookie": cookie, "Origin": "http://127.0.0.1"}
    assert _open(base + "/approve", form_k, same)[0] == 404
    # The tap path answers nothing to a token that was never issued, cookie or not.
    assert _open(base + "/tap/not-a-token", headers={"Cookie": cookie})[0] == 404


def test_the_session_key_stays_out_of_the_terminal_when_a_browser_opens(capsys):
    url = "http://127.0.0.1:7425/?k=" + "s" * 32
    opened: list[str] = []
    assert _launch(url, True, opener=lambda u: opened.append(u) or True)
    assert opened == [url] and "s" * 32 not in capsys.readouterr().out
    # no browser (or --no-open) at a terminal: the only way in is the printed URL
    assert not _launch(url, True, opener=lambda u: False, terminal=True)
    assert url in capsys.readouterr().out
    assert not _launch(url, False, opener=lambda u: pytest.fail("--no-open"), terminal=True)
    assert url in capsys.readouterr().out
    # not a terminal (an agent's shell tool): the key is never printed
    assert not _launch(url, False, terminal=False)
    assert "s" * 32 not in capsys.readouterr().out


def test_item_page_puts_the_acts_last_and_quarantine_is_an_outline(boat):
    b, item = boat
    body = b.item(item.id)[1]
    assert body.index("lifecycle") < body.index("Approve — mark verified")
    assert ".badge.quarantined{color:var(--egz-alarm);border-color:var(--egz-alarm)}" in body


def test_a_tap_for_an_item_gone_meanwhile_answers_uniformly(boat):
    b, item = boat
    token = _to_tap(b, item.id)
    b.c.backend.tombstone(item.id)
    b.tap_post(token, "arm")
    status, page = b.tap_post(token, "confirm")
    assert status == 200 and "This request is no longer valid." in page
