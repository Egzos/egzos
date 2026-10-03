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


def test_approve_needs_two_presses_and_is_audited(boat, monkeypatch):
    monkeypatch.delenv("EGZOS_STEP_UP_WINDOW_SECONDS", raising=False)
    b, item = boat
    # One request — what a script holding the key would send — arms and does nothing else.
    _, _, redirect = b.act("/approve", {"ref": item.id, "back": "/pending", "step": "arm"})
    assert "Confirm+signature" in redirect and b.c.backend.get(item.id).status == "unverified"
    assert "Confirm signature" in b.pending()[1]
    _, _, redirect = b.act("/approve", {"ref": item.id, "back": "/pending", "step": "confirm"})
    assert redirect.startswith("/pending?ok=Approved")
    assert b.c.backend.get(item.id).status == "verified"
    assert b.c.ledger.tail(1)[0]["event"] == "approval.promote"
    signed = _step_ups(b.c)[-1]
    assert signed["via"] == "lifeboat" and signed["outcome"] == "approved"
    assert signed["window_closes"] and b.c.ledger.verify()["ok"]


def test_a_confirm_without_an_arm_only_arms(boat, monkeypatch):
    monkeypatch.setenv("EGZOS_STEP_UP_WINDOW_SECONDS", "0")
    b, item = boat
    b.act("/approve", {"ref": item.id, "back": "/pending", "step": "confirm"})
    assert b.c.backend.get(item.id).status == "unverified"
    assert _step_ups(b.c) == []


def test_an_open_window_covers_the_next_approval_in_one_press(boat, monkeypatch):
    monkeypatch.delenv("EGZOS_STEP_UP_WINDOW_SECONDS", raising=False)
    b, item = boat
    token = b.c.require_token()
    other = b.c.store.add(body="second", token=token, actor=OWNER, principal=token.principal)
    b.c.backend.put(other)
    for step in ("arm", "confirm"):
        b.act("/approve", {"ref": item.id, "back": "/pending", "step": step})
    # `other` sits in its own inbox thread: the same ring pair (thread → thread)
    b.act("/approve", {"ref": other.id, "back": "/pending", "step": "arm"})
    assert b.c.backend.get(other.id).status == "verified"
    assert _step_ups(b.c)[-1]["outcome"] == "window"


def test_back_is_kept_on_this_origin(boat):
    b, item = boat
    for back in ("https://evil.test/", "//evil.test/x"):
        _, _, redirect = b.act("/approve", {"ref": item.id, "back": back})
        assert redirect.startswith("/pending?")


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
