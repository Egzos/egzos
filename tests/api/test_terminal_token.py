# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""identity.md §3a, §5 and rest.md §4.2-§4.4, §6: a terminal's token at the door. It is its
person, with the person's grant as it stands, and every entry its request appends names the
terminal it came through, never a later request's. It gives no one access: the routes that give
access, or keep or remove a confirm credential, refuse it before any leg and before its body is
read. On every other confirm-gated act it is served the first leg, with no assertion offered, and
concludes no second leg by either proof. What is issued to it is its own: an open upload, a
`BlobGrant`, while an orphan of its own is its person's to see and discard."""

from __future__ import annotations

import hashlib
import time

import jwt
import pytest
from authenticator import SoftAuthenticator
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from egzos.api.app import create_app
from egzos.container import OWNER, Container
from egzos.identity import Jwks
from egzos.store.uploads import UPLOAD_TTL_SECONDS

EGZOS = "https://egzos.io"
ISSUER = "https://project.supabase.co/auth/v1"
NOT_FOUND = b'{"error":"not_found"}'
UNAUTHORIZED = b'{"error":"unauthorized"}'
KW = {"actor": OWNER, "principal": "interactive"}
DATA = b"a note, as a file\n"


class Clock:
    def __init__(self):
        self.now = time.time()

    def __call__(self):
        return self.now


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    box.clock = box.uploads.clock = Clock()
    return box


@pytest.fixture
def door(c):
    return TestClient(create_app(c))


@pytest.fixture
def sign(c):
    """Provider sign-ins: alice an admin over everything with a laptop and a desk, bob a
    contributor with an agent of his own."""
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = {**jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True), "kid": "k1",
           "alg": "ES256"}
    c.set_config("identity.issuer", ISSUER, token=c.owner)
    c.set_config("identity.client_id", "box", token=c.owner)
    jwks = Jwks("x", fetch=lambda url: {"keys": [jwk]})
    c.identity._jwks_for = lambda url: jwks
    c.identity.grant_user("alice", name="Alice", role="admin", scopes=["*"], **KW)
    c.identity.grant_user("bob", name="Bob", role="contributor", scopes=["*"], **KW)
    for client_id, sub in (("laptop", "alice"), ("desk", "alice"), ("bob-laptop", "bob")):
        _terminal(c, client_id, sub)
    c.backend.put_agent_registration({
        "client_id": "helper", "sub": "bob", "name": "Helper", "capabilities": ["fetch"],
        "scopes": ["*"], "created_at": "2026-10-23T00:00:00Z", "revoked": False})

    def headers(sub="alice", client_id="box"):
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": "authenticated", "exp": now + 600, "iat": now,
                  "sub": sub, "client_id": client_id,
                  "amr": [{"method": "otp", "timestamp": now - 30}]}
        value = jwt.encode(claims, key, algorithm="ES256", headers={"kid": "k1"})
        return {"Authorization": f"Bearer {value}", "Origin": EGZOS}

    return headers


def _terminal(c, client_id, sub, revoked=False):
    c.backend.put_agent_registration({
        "client_id": client_id, "sub": sub, "kind": "terminal", "name": client_id.title(),
        "created_at": "2026-11-01T00:00:00Z", "revoked": revoked})


def _events(c, name):
    return [e for e in c.ledger.tail(3000) if e["event"] == name]


def _head(c):
    return c.ledger.tail(1)[-1]["seq"]


def _since(c, head):
    return c.ledger.tail(_head(c) - head)


def _button(first, **body):
    return {**body, "confirm": {"challenge": first["challenge"], "proof": "button"}}


def _node(c, kind, name, parent=None):
    return c.nodes.create(kind, name, parent=parent or c.nodes.user_root(), token=c.owner, **KW)


def _enrol(door, h):
    """A confirm credential of the person's own, from their browser: their every confirm now
    needs the biometric, and a browser's first leg offers it."""
    phone = SoftAuthenticator(EGZOS)
    enrol = door.post("/v1/credentials", headers=h).json()
    made = door.post("/v1/credentials", headers=h, json={
        "challenge": enrol["challenge"], "attestation": phone.create(enrol["webauthn"]),
        "confirm": {"challenge": enrol["confirm"]["challenge"], "proof": "button"}})
    assert made.status_code == 200, made.content
    return phone, made.json()["credential"]["id"]


# -- a terminal's token gives no one access --------------------------------------------------------
def test_the_routes_that_give_access_refuse_a_terminals_token_before_any_leg_or_body(c, door,
                                                                                     sign):
    _phone, credential = _enrol(door, sign())
    routes = [("POST", "/v1/grants"), ("POST", "/v1/agents"), ("POST", "/v1/terminals"),
              ("POST", "/v1/credentials"), ("DELETE", f"/v1/credentials/{credential}")]
    junk = b"{not json"  # read, it would be §3's 400; unread, the refusal is all there is
    for method, path in routes:  # in a browser, alice's body is read, and refused as malformed
        r = door.request(method, path, headers={**sign(), "Content-Type": "application/json"},
                         content=junk)
        assert r.status_code == 400, path
    laptop = {**sign(client_id="laptop"), "Content-Type": "application/json"}
    head = _head(c)
    for method, path in routes:
        for body in (junk, b'{"sub": "dan", "name": "Dan", "role": "reader", "scopes": ["*"]}',
                     b'{"authorization_id": "a", "client_id": "new", "name": "New"}', b""):
            r = door.request(method, path, headers=laptop, content=body)
            assert (r.status_code, r.content) == (404, NOT_FOUND), (path, body)
    # Each refusal is one read with nothing in it, through the laptop; no challenge was issued.
    new = _since(c, head)
    assert {(e["event"], e["actor"], e["details"]["terminal"]) for e in new} == {
        ("context.fetch", "user:alice", "laptop")}
    assert len(new) == 4 * len(routes) and all(e["details"]["items"] == [] for e in new)
    assert not [e for e in new if "confirm_for" in e["details"]]
    assert c.backend.get_user_grant("dan") is None
    assert c.backend.get_agent_registration("new", "alice") is None
    assert len(c.confirm.credentials("user:alice")) == 1


# -- a terminal concludes no gated act -------------------------------------------------------------
@pytest.fixture
def acts(c, door, sign):
    """One of each confirm-gated act a terminal is served the first leg of, as (method, path,
    body, done): whether it landed. Alice has a confirm credential, so her browser is offered an
    assertion; her laptop never is."""
    root = c.nodes.user_root()
    mine, ours = _node(c, "project", "mine"), _node(c, "project", "ours")
    c.identity.grant_user("dan", name="Dan", role="reader", scopes=[ours.id], **KW)
    note, other = (c.store.add(body=b, scope=mine, token=c.owner, **KW) for b in ("n", "o"))
    curator = c.auth.mint(principal="client", owner=OWNER, client="agent", role="curator",
                          scopes=["*"], actor=OWNER, by_principal="interactive")
    bearer = {"Authorization": f"Bearer {curator.secret}"}
    parked = [door.post(f"/v1/items/{i.id}/move", headers=bearer,
                        json={"to": ours.id}).json()["proposal"] for i in (note, other)]
    loose = c.store.add(body="unverified", scope=root, token=c.owner, **KW)
    kept = c.store.add(body="curated", scope=mine, token=c.owner, **KW)
    c.trust.promote(kept, token=c.owner, actor=OWNER)
    phone, _credential = _enrol(door, sign())

    def status(pid):
        return c.backend.get_proposal(pid)["status"]

    def live(client_id, sub):
        return not c.backend.get_agent_registration(client_id, sub)["revoked"]

    acts = {
        "move": ("POST", f"/v1/items/{note.id}/move", {"to": ours.id},
                 lambda: c.store.get(note.id).scope == ours.id),
        "copy": ("POST", f"/v1/items/{note.id}/copy", {"to": ours.id},
                 lambda: bool(_events(c, "item.copy"))),
        "approve": ("POST", f"/v1/pending/{parked[0]}/approve", {},
                    lambda: status(parked[0]) != "open"),
        "deny": ("POST", f"/v1/pending/{parked[1]}/deny", {},
                 lambda: status(parked[1]) != "open"),
        "promote": ("POST", f"/v1/items/{loose.id}/promote", {},
                    lambda: c.store.get(loose.id).status == "verified"),
        "tombstone": ("DELETE", f"/v1/items/{kept.id}", {}, lambda: c.store.get(kept.id) is None),
        "grant.revoke": ("DELETE", "/v1/grants/bob", {},
                         lambda: c.backend.get_user_grant("bob")["revoked"]),
        "agent.revoke": ("DELETE", "/v1/agents/helper?sub=bob", {},
                         lambda: not live("helper", "bob")),
        "terminal.revoke": ("DELETE", "/v1/terminals/bob-laptop?sub=bob", {},
                            lambda: not live("bob-laptop", "bob")),
    }
    return acts, phone


@pytest.mark.parametrize("act", ["move", "copy", "approve", "deny", "promote", "tombstone",
                                 "grant.revoke", "agent.revoke", "terminal.revoke"])
def test_a_terminal_is_served_the_first_leg_and_concludes_no_second(c, door, sign, acts, act):
    (method, path, body, done), phone = acts[0][act], acts[1]
    browser = door.request(method, path, headers=sign(), json=body).json()
    assert browser["result"] == "confirm" and browser["webauthn"] is not None  # she could confirm
    laptop = sign(client_id="laptop")
    first = door.request(method, path, headers=laptop, json=body).json()
    assert (first["result"], first["webauthn"]) == ("confirm", None)  # finished in a browser
    shown = _events(c, "context.fetch")[-1]
    assert (shown["actor"], shown["details"]["terminal"]) == ("user:alice", "laptop")
    # The button, and a biometric made by her own authenticator, both conclude refused.
    assertion = phone.get(browser["webauthn"])
    proofs = [{"challenge": first["challenge"], "proof": "button"},
              {"challenge": None, "proof": "biometric", "assertion": assertion}]
    for proof in proofs:
        proof["challenge"] = proof["challenge"] or first["challenge"]
        again = door.request(method, path, headers=laptop, json={**body, "confirm": proof}).json()
        assert (again["result"], again["webauthn"]) == ("confirm", None)
        assert again["challenge"] != first["challenge"]
        step_up = _events(c, "step_up")[-1]
        assert (step_up["actor"], step_up["details"]["outcome"], step_up["details"]["reason"],
                step_up["details"]["proof"], step_up["details"]["terminal"]) == (
            "user:alice", "refused", "terminal", proof["proof"], "laptop")
        first = again
    assert not done()
    # In her browser, the same act concludes with her own authenticator.
    browser = door.request(method, path, headers=sign(), json=body).json()
    r = door.request(method, path, headers=sign(), json={**body, "confirm": {
        "challenge": browser["challenge"], "proof": "biometric",
        "assertion": phone.get(browser["webauthn"])}})
    assert r.status_code == 200 and r.json()["result"] != "confirm", r.content
    assert done()


def test_a_terminal_narrows_its_own_persons_access_at_once(c, door, sign):
    """Ending a registration that serves its person is never gated (identity.md §4, §8)."""
    laptop = sign(client_id="laptop")
    assert door.delete("/v1/terminals/desk", headers=laptop).json() == {"result": "revoked"}
    assert not _events(c, "step_up")
    assert door.get("/v1/fetch", headers=sign(client_id="desk")).content == UNAUTHORIZED
    assert door.get("/v1/fetch", headers=laptop).status_code == 200


# -- attribution -----------------------------------------------------------------------------------
def test_every_entry_of_a_terminals_request_names_it_and_no_later_request_does(c, door, sign):
    p = _node(c, "project", "p")
    head = _head(c)
    laptop = sign("bob", client_id="bob-laptop")
    item = door.post("/v1/items", headers=laptop, json={"body": "from the laptop", "scope": p.id})
    assert item.status_code == 200
    door.get(f"/v1/items/{item.json()['item']['id']}", headers=laptop)
    door.get("/v1/items/01ABSENTABSENTABSENTABSENT", headers=laptop)  # a probe, too
    door.get("/v1/agents", headers=laptop)
    through = _since(c, head)
    assert [e["event"] for e in through] == ["item.add", "context.fetch", "context.fetch",
                                             "context.fetch"]
    assert {(e["actor"], e["principal"], e["details"]["terminal"]) for e in through} == {
        ("user:bob", "interactive", "bob-laptop")}
    assert not any("for" in e["details"] for e in through)
    # The next requests, bob in a browser, his agent, alice at another terminal: their own.
    head = _head(c)
    door.get(f"/v1/fetch?scope={p.id}", headers=sign("bob"))
    door.get(f"/v1/fetch?scope={p.id}", headers=sign("bob", client_id="helper"))
    door.get(f"/v1/fetch?scope={p.id}", headers=sign(client_id="laptop"))
    door.get(f"/v1/fetch?scope={p.id}", headers={"Authorization": f"Bearer {c.owner.secret}"})
    after = _since(c, head)
    assert [(e["actor"], e["details"].get("terminal"), e["details"].get("for")) for e in after] == [
        ("user:bob", None, None), ("agent:helper", None, "user:bob"),
        ("user:alice", "laptop", None), (OWNER, None, None)]


# -- uploads (rest.md §4.4) ------------------------------------------------------------------------
def _upload(door, h, scope):
    r = door.post("/v1/uploads", headers=h, json={
        "scope": scope, "name": "note.txt", "mime": "text/plain", "size": len(DATA),
        "sha256": hashlib.sha256(DATA).hexdigest()})
    uid = r.json()["upload"]
    assert door.put(f"/v1/uploads/{uid}", headers=h, content=DATA).status_code == 200
    return uid


def test_an_open_upload_is_its_terminals_and_an_orphan_its_persons(c, door, sign):
    p = _node(c, "project", "p")
    laptop, bob = sign("bob", client_id="bob-laptop"), sign("bob")
    uid = _upload(door, laptop, p.id)
    upload = c.backend.get_upload(uid)
    assert (upload["principal"], upload["actor"]) == ("terminal:bob-laptop:bob", "user:bob")
    # Open, it is the laptop's alone: bob's browser cannot send its bytes or discard it.
    assert door.put(f"/v1/uploads/{uid}", headers=bob, content=DATA).content == NOT_FOUND
    assert door.delete(f"/v1/uploads/{uid}", headers=bob).content == NOT_FOUND
    c.clock.now += UPLOAD_TTL_SECONDS

    def listed(h):
        return [u["upload"] for u in door.get("/v1/pending", headers=h).json()["uploads"]]

    # Orphaned, it is listed to bob and to the laptop, and to an admin; never to his agent's
    # reader or to alice's own terminals as bob's.
    assert listed(bob) == listed(laptop) == listed(sign()) == [uid]
    assert listed(sign(client_id="laptop")) == [uid]  # alice, an admin over everything
    _terminal(c, "bob-desk", "bob")
    assert listed(sign("bob", client_id="bob-desk")) == []  # another terminal: not its own
    assert door.delete(f"/v1/uploads/{uid}", headers=sign("bob", client_id="bob-desk")).content == (
        NOT_FOUND)
    assert door.delete(f"/v1/uploads/{uid}", headers=bob).json() == {"result": "discarded"}
    discarded = _events(c, "upload.discard")[-1]
    assert (discarded["actor"], discarded["subject"], discarded["details"]["opener"]) == (
        "user:bob", uid, "user:bob")
    assert "terminal" not in discarded["details"]  # bob, in a browser
    assert listed(bob) == listed(laptop) == []


# -- BlobGrant (rest.md §6) ------------------------------------------------------------------------
def test_a_grant_minted_through_a_terminal_is_its_own_and_ends_with_it(c, door, sign, tmp_path):
    p = _node(c, "project", "p")
    files = []
    for n in range(2):
        path = tmp_path / f"a{n}.bin"
        path.write_bytes(bytes([n]) * 4096)
        files.append(c.store.add(file=path, scope=p, token=c.owner, **KW))
    laptop = sign("bob", client_id="bob-laptop")
    urls = [door.get(f"/v1/items/{f.id}", headers=laptop).json()["grant_url"] for f in files]
    assert all("token=terminal%3Abob-laptop%3Abob" in u or "token=terminal:bob-laptop:bob" in u
               for u in urls)
    assert door.get(urls[0]).status_code == 200  # no bearer: the descriptor alone
    pulled = _events(c, "blob.pull")[-1]
    assert (pulled["actor"], pulled["details"]["terminal"]) == ("user:bob", "bob-laptop")
    assert door.delete("/v1/terminals/bob-laptop", headers=sign("bob")).json()["result"] == (
        "revoked")
    head = _head(c)
    assert door.get(urls[1]).content == NOT_FOUND  # ended since the mint: check 5
    (refused,) = _since(c, head)
    assert (refused["event"], refused["actor"], refused["details"]["terminal"],
            refused["details"]["check"]) == ("context.fetch", "user:bob", "bob-laptop", 5)
