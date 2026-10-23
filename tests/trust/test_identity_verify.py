# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""identity.md §3: a provider token passes seven checks, in order, or gets the one answer (`None`).

The provider is a local ES256 key pair and an in-memory key set, so every check is driven from a
token this file signs: nothing here reaches a network.
"""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from egzos.container import OWNER, Container
from egzos.identity import (
    JWKS_REFETCH_SECONDS,
    SKEW_SECONDS,
    TOKEN_MAX_CHARS,
    GrantToken,
    Jwks,
)

ISSUER = "https://project.supabase.co/auth/v1"
CLIENT = "container-client"
AGENT = "agent-client"
ALICE = "11111111-1111-1111-1111-111111111111"
BOB = "22222222-2222-2222-2222-222222222222"


def _jwk(private, kid: str, alg: str) -> dict:
    algorithm = jwt.algorithms.ECAlgorithm if alg.startswith("ES") else jwt.algorithms.RSAAlgorithm
    jwk = algorithm.to_jwk(private.public_key(), as_dict=True)
    return {**jwk, "kid": kid, "alg": alg, "use": "sig"}


@pytest.fixture
def key():
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def box(tmp_path, key):
    c = Container(tmp_path)
    owner = c.init()
    c.set_config("identity.issuer", ISSUER, token=owner)
    c.set_config("identity.client_id", CLIENT, token=owner)
    c.keyset = {"keys": [_jwk(key, "k1", "ES256")]}
    c.fetches = []

    def fetch(url):
        c.fetches.append(url)
        return c.keyset

    c.identity._jwks_for = lambda url: c.__dict__.setdefault("_jwks", Jwks(url, fetch=fetch))
    c.identity.grant_user(ALICE, name="alice", role="admin", scopes=["*"], actor=OWNER,
                          principal="interactive")
    c.owner = owner
    return c


def _claims(**over):
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": "authenticated", "exp": now + 600, "iat": now, "sub": ALICE,
              "client_id": CLIENT, "role": "authenticated"}
    claims.update(over)
    return {k: v for k, v in claims.items() if v is not None}


def _sign(key, *, kid="k1", alg="ES256", headers=None, **over):
    return jwt.encode(_claims(**over), key, algorithm=alg, headers={"kid": kid, **(headers or {})})


def _register(c, client_id=AGENT, sub=ALICE, *, capabilities=("fetch", "remember"),
              scopes=("*",), revoked=False):
    c.backend.put_agent_registration({
        "client_id": client_id, "sub": sub, "name": "an agent", "capabilities": list(capabilities),
        "scopes": list(scopes), "created_at": "2026-10-23T00:00:00Z", "revoked": revoked,
    })


# -- a token that passes ---------------------------------------------------------------------------
def test_a_person_with_a_grant_is_the_interactive_principal(box, key):
    who = box.identity.verify(_sign(key))
    assert isinstance(who, GrantToken)
    assert (who.id, who.principal, who.owner, who.sub) == (f"user:{ALICE}", "interactive",
                                                            f"user:{ALICE}", ALICE)
    assert who.scopes == ["*"] and "admin" in who.capabilities
    assert who.acting_for is None


def test_an_agent_is_the_client_principal_and_names_who_it_acts_for(box, key):
    _register(box)
    who = box.identity.verify(_sign(key, client_id=AGENT))
    assert (who.principal, who.owner, who.acting_for) == ("client", f"agent:{AGENT}",
                                                          f"user:{ALICE}")
    assert who.capabilities == ["fetch", "remember"]


def test_an_audience_list_containing_the_audience_passes(box, key):
    assert box.identity.verify(_sign(key, aud=["other", "authenticated"])) is not None


def test_skew_is_allowed_up_to_sixty_seconds(box, key):
    now = int(time.time())
    assert box.identity.verify(_sign(key, exp=now - SKEW_SECONDS + 5)) is not None
    assert box.identity.verify(_sign(key, iat=now + SKEW_SECONDS - 5)) is not None


# -- every failure is one answer -------------------------------------------------------------------
def test_no_provider_configured_accepts_no_provider_token(tmp_path, key):
    c = Container(tmp_path)
    c.init()
    assert c.identity.provider() is None
    assert c.identity.verify(_sign(key)) is None


#: Offsets from the moment the test runs, never from collection: a long suite would age them.
LATE, EARLY = object(), object()


@pytest.mark.parametrize(
    "over",
    [
        {"iss": "https://elsewhere.supabase.co/auth/v1"},
        {"iss": ISSUER + "/"},
        {"aud": "anon"},
        {"aud": ["anon"]},
        {"exp": LATE},
        {"iat": EARLY},
        {"exp": True},
        {"exp": "soon"},
        {"iat": None},
        {"sub": None},
        {"sub": ""},
        {"client_id": None},
        {"client_id": "another-container"},
        {"sub": BOB},
    ],
    ids=["issuer", "issuer-slash", "aud", "aud-list", "expired", "iat-future", "exp-bool",
         "exp-str", "no-iat", "no-sub", "empty-sub", "no-client", "foreign-client", "no-grant"],
)
def test_each_failed_check_is_none(box, key, over):
    now = int(time.time())
    when = {LATE: now - SKEW_SECONDS - 5, EARLY: now + SKEW_SECONDS + 5}
    over = {k: when.get(v, v) if not isinstance(v, list) else v for k, v in over.items()}
    assert box.identity.verify(_sign(key, **over)) is None


def test_a_bare_session_with_no_client_id_is_refused(box, key):
    # §3a: a session issued to egzos.io itself is bound to no container.
    assert box.identity.verify(_sign(key, client_id=None)) is None


def test_another_key_or_an_unknown_kid_is_refused(box, key):
    stranger = ec.generate_private_key(ec.SECP256R1())
    assert box.identity.verify(_sign(stranger)) is None
    assert box.identity.verify(_sign(key, kid="k9")) is None
    assert box.identity.verify(_sign(key, kid="")) is None


def test_a_symmetric_token_is_refused_even_naming_a_real_kid(box, key):
    # §2: an HS256 token can only be checked with a shared secret; none is ever trusted.
    forged = jwt.encode(_claims(), "a shared secret of thirty-two bytes", algorithm="HS256",
                        headers={"kid": "k1"})
    assert box.identity.verify(forged) is None


def test_an_unsigned_token_is_refused(box):
    unsigned = jwt.encode(_claims(), None, algorithm="none", headers={"kid": "k1"})
    assert box.identity.verify(unsigned) is None


def test_the_algorithm_comes_from_the_key_not_the_header(box):
    # An RSA key published under kid k2, and a token signed with it but claiming ES256: the key
    # says RS256, so ES256 is not tried, and the configured list decides whether RS256 is.
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    box.keyset = {"keys": [*box.keyset["keys"], _jwk(rsa_key, "k2", "RS256")]}
    good = _sign(rsa_key, kid="k2", alg="RS256")
    assert box.identity.verify(good) is not None
    owner = box.owner
    box.set_config("identity.algorithms", "ES256", token=owner)
    assert box.identity.verify(good) is None


def test_symmetric_keys_in_the_set_are_ignored(box, key):
    box.keyset = {"keys": [{"kty": "oct", "kid": "k1", "k": "c2VjcmV0", "alg": "HS256"}]}
    box.__dict__.pop("_jwks", None)
    assert box.identity.verify(_sign(key)) is None


def test_an_oversized_value_is_refused_before_parsing(box):
    assert box.identity.verify("x" * (TOKEN_MAX_CHARS + 1)) is None
    assert box.identity.verify("") is None
    assert box.identity.verify("not.a.jwt") is None


def test_a_revoked_grant_is_refused_on_the_next_request(box, key):
    token = _sign(key)
    box.identity.grant_user(BOB, name="bob", role="admin", scopes=["*"], actor=OWNER,
                            principal="interactive")
    assert box.identity.verify(token) is not None
    assert box.identity.revoke_user(ALICE, actor=OWNER, principal="interactive")
    assert box.identity.verify(token) is None


# -- agents (§4) -----------------------------------------------------------------------------------
def test_an_unregistered_or_revoked_agent_is_refused(box, key):
    assert box.identity.verify(_sign(key, client_id=AGENT)) is None
    _register(box, revoked=True)
    assert box.identity.verify(_sign(key, client_id=AGENT)) is None


def test_a_registration_serves_only_its_own_user(box, key):
    _register(box, sub=ALICE)
    box.identity.grant_user(BOB, name="bob", role="reader", scopes=["*"], actor=OWNER,
                            principal="interactive")
    assert box.identity.verify(_sign(key, client_id=AGENT, sub=BOB)) is None


def test_an_agent_never_holds_more_than_its_user(box, key):
    box.identity.grant_user(BOB, name="bob", role="reader", scopes=["*"], actor=OWNER,
                            principal="interactive")
    _register(box, sub=BOB, capabilities=("fetch", "remember", "admin"))
    who = box.identity.verify(_sign(key, client_id=AGENT, sub=BOB))
    assert who.capabilities == ["fetch"]


def test_agent_scopes_are_the_overlap_of_registration_and_grant(box, key):
    root = box.nodes.user_root()
    kw = {"token": box.owner, "actor": OWNER, "principal": "interactive"}
    project = box.nodes.create("project", "p", parent=root, **kw)
    thread = box.nodes.create("thread", "t", parent=project, **kw)
    other = box.nodes.create("project", "q", parent=root, **kw)
    box.identity.grant_user(BOB, name="bob", role="contributor", scopes=[project.id],
                            actor=OWNER, principal="interactive")
    _register(box, sub=BOB, scopes=(thread.id, other.id))
    who = box.identity.verify(_sign(key, client_id=AGENT, sub=BOB))
    assert who.scopes == [thread.id]
    _register(box, sub=BOB, scopes=(other.id,))
    assert box.identity.verify(_sign(key, client_id=AGENT, sub=BOB)) is None


# -- the key set (§3 check 1) ----------------------------------------------------------------------
def test_an_unknown_kid_refetches_at_most_once_a_minute():
    clock = [1000.0]
    calls = []
    jwks = Jwks("https://p/jwks", fetch=lambda u: calls.append(u) or {"keys": []},
                clock=lambda: clock[0])
    for _ in range(50):
        assert jwks.key("nope") is None
    assert len(calls) == 1
    clock[0] += JWKS_REFETCH_SECONDS
    assert jwks.key("nope") is None
    assert len(calls) == 2


def test_an_unreachable_provider_fails_closed():
    def down(url):
        raise OSError("unreachable")

    assert Jwks("https://p/jwks", fetch=down).key("k1") is None


def test_the_key_set_is_read_from_the_issuer(box, key):
    box.identity.verify(_sign(key))
    assert box.fetches == [ISSUER + "/.well-known/jwks.json"]
