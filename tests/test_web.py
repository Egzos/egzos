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
from egzos.web import Lifeboat, make_handler


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


def test_approve_promotes_and_is_audited(boat):
    b, item = boat
    status, _, redirect = b.act("/approve", {"ref": item.id, "back": "/pending"})
    assert redirect.startswith("/pending?ok=")
    assert b.c.backend.get(item.id).status == "verified"
    assert b.c.ledger.tail(1)[0]["event"] == "approval.promote"
    assert b.c.ledger.verify()["ok"]


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
