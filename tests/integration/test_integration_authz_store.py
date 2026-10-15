# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The authorization server's modules against the real sqlite store and the real ledger (#266, F28).

Every `authz` slice was unit-tested against a fake of the store it reaches. This suite wires the
same functions to one `SqliteBackend` on a temp path, which is `ContainerState`, `ASState` and
`ASGateState` at once (storage.md §3.1 rule 4), and to a `Ledger` on that backend. Nothing with a
real implementation on `main` is faked here. The one stand-in is `LoginSecret`, whose provisioning
is #143's and has no implementation yet.

A seam is the place two sides' unit tests can each pass while the pair disagrees: #265's review
found Trust's fake `revoke_family` returning every id in a family where the store returns only the
ids it newly revoked (#214). So each flow below asserts what lands in the store and on the chain,
not only what the function returns, and ends with `_assert_clean`: the chain verifies by the
ledger's own walk, and no credential value appears in the chain or in the sqlite file's bytes.

Three reads go beneath the protocols on purpose. `ASState` has no read of a refresh record that
does not spend it, so `_refresh_rows` reads the store's table through a second, read-only sqlite
connection; `_nothing_stored` counts the AS tables the same way, because no protocol read lists
them; and the byte scan reads the database file and its WAL. Both are the store's layout,
pinned here as of #265: a rename in `backends/sqlite.py` fails this suite loudly, never silently.
"""

from __future__ import annotations

import hmac
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from egzos._types import (
    AS_THROTTLE_SURFACES,
    PRINCIPAL_NONE_EVENTS,
    ASGrant,
    ClientRegistration,
)
from egzos.authz import (
    codes,
    decided,
    device_authorization,
    device_entry,
    gate,
    login,
    pkce,
    pretrust,
    revoke,
    sessions,
    token_endpoint,
    tokens,
    values,
)
from egzos.backends.sqlite import SqliteBackend
from egzos.ledger import Ledger

T0 = datetime(2026, 10, 15, 9, 0, 0, tzinfo=UTC)
OWNER = "owner"
BROWSER = "egzos.io"
CLI = "egzos-cli"
REDIRECT = "https://egzos.io/connect/callback"
VERIFIER = "v" * 43  # RFC 7636's minimum length; the challenge is its S256
CHALLENGE = pkce.s256(VERIFIER)
FORM = "application/x-www-form-urlencoded"
KEY = b"k" * 32  # a fixture device-code key; provisioning the real one is #143's
ISSUER = "https://box.example/"
CONTAINER_SECRET = "a-container-secret-for-the-seam-suite"


class _Secret:
    """`login.LoginSecret`, the one stand-in: #143 has not provisioned the container secret."""

    def verify(self, presented: str) -> bool:
        return bool(presented) and hmac.compare_digest(
            presented.encode(), CONTAINER_SECRET.encode()
        )


@dataclass
class Box:
    backend: SqliteBackend
    ledger: Ledger
    path: Path


@pytest.fixture
def box(tmp_path: Path) -> Box:
    backend = SqliteBackend(tmp_path / "container.db")
    return Box(backend, Ledger(backend), backend.path)


def _chain(box: Box) -> list[dict[str, Any]]:
    return list(box.backend.audit_iter())


def _events(box: Box, event: str) -> list[dict[str, Any]]:
    return [e for e in _chain(box) if e["event"] == event]


def _read(box: Box, sql: str, *args: Any) -> list[tuple[Any, ...]]:
    # `closing`, not `with sqlite3.connect()`: the latter commits and never closes (#267's review).
    with closing(sqlite3.connect(f"file:{box.path}?mode=ro", uri=True)) as db:
        return db.execute(sql, args).fetchall()


def _refresh_rows(box: Box, family_id: str) -> list[dict[str, Any]]:
    rows = _read(box, "SELECT doc FROM as_refresh WHERE family_id=?", family_id)
    return [json.loads(doc) for (doc,) in rows]


def _assert_clean(box: Box, *credentials: str) -> None:
    """The chain verifies, and no credential value is in it or anywhere in the sqlite file."""
    assert box.ledger.verify()["ok"] is True
    chain = json.dumps(_chain(box))
    files = [p for p in box.path.parent.iterdir() if p.name.startswith(box.path.name)]
    assert box.path in files
    raw = b"".join(p.read_bytes() for p in files)
    for value in credentials:
        assert value, "an empty credential proves nothing"
        assert value not in chain
        assert value.encode() not in raw


def _code_grant(**over: Any) -> ASGrant:
    return ASGrant(
        capabilities=["fetch", "remember"],
        scopes=["*"],
        principal="interactive",
        grant_expires_at="2026-11-14T09:00:00Z",
        **over,
    )


def _code_flow(box: Box, *, now: datetime = T0) -> tuple[tokens.Issued, str, str]:
    """A session, a code against it, the code redeemed: the issued pair, the code, the session."""
    session = sessions.establish(box.backend, now=now)
    code = codes.issue(
        box.backend,
        client_id=BROWSER,
        redirect_uri=REDIRECT,
        code_challenge=pkce.s256(VERIFIER),
        session_hash=values.digest(session),
        grant=_code_grant(),
        now=now,
    )
    issued = tokens.exchange_code(
        box.backend,
        box.ledger,
        code=code,
        client_id=BROWSER,
        redirect_uri=REDIRECT,
        code_verifier=VERIFIER,
        owner=OWNER,
        now=now,
    )
    assert issued is not None
    return issued, code, session


# -- sessions and login (§10.1, §10.2, §11.7) ----------------------------------------------------


def test_login_establishes_a_session_the_real_gate_resolves_touches_and_ends(box: Box):
    answer = login.attempt(
        box.backend,
        box.ledger,
        _Secret(),
        credential=CONTAINER_SECRET,
        continue_value="/",
        now=T0,
    )
    assert answer.session is not None and answer.location is not None
    digest = values.digest(answer.session)
    assert box.backend.get_session(digest)["last_seen_at"] == "2026-10-15T09:00:00Z"

    later = T0 + timedelta(minutes=10)
    assert sessions.resolve(box.backend, answer.session, now=later) == digest
    assert box.backend.get_session(digest)["last_seen_at"] == "2026-10-15T09:10:00Z"
    assert box.backend.get_session(digest)["created_at"] == "2026-10-15T09:00:00Z"

    sessions.end(box.backend, answer.session)
    assert box.backend.get_session(digest) is None
    assert sessions.resolve(box.backend, answer.session, now=later) is None

    (entry,) = _events(box, "authz.login")
    assert entry["principal"] == "none" and entry["actor"] == "login"
    assert entry["details"] == {"outcome": "established"}
    _assert_clean(box, answer.session, CONTAINER_SECRET)


def test_a_wrong_credential_stores_no_session_and_appends_one_failed_login(box: Box):
    answer = login.attempt(
        box.backend, box.ledger, _Secret(), credential="not-it", continue_value="/", now=T0
    )
    assert answer == login.Login(None, None)
    assert _read(box, "SELECT COUNT(*) FROM as_sessions") == [(0,)]
    (entry,) = _events(box, "authz.login")
    assert entry["principal"] == "none"
    assert entry["details"] == {"outcome": "failed", "cause": "wrong"}
    _assert_clean(box, "not-it")


def test_a_session_past_its_idle_clock_is_ended_in_the_real_store(box: Box):
    value = sessions.establish(box.backend, now=T0)
    assert sessions.resolve(box.backend, value, now=T0 + timedelta(minutes=31)) is None
    assert box.backend.get_session(values.digest(value)) is None
    _assert_clean(box, value)


# -- the code flow (§2, §9.3 row 1) --------------------------------------------------------------


def test_a_code_redeemed_against_the_real_store_mints_one_token_and_one_mint(box: Box):
    issued, code, session = _code_flow(box)

    stored = box.backend.get_token(issued.token.id)
    assert stored is not None and not stored.revoked
    assert stored.secret_hash == values.digest(issued.access_token)
    assert (stored.owner, stored.client, stored.principal) == (OWNER, BROWSER, "interactive")
    assert [t.id for t in box.backend.list_tokens()] == [issued.token.id]

    (mint,) = _events(box, "token.mint")
    assert mint["subject"] == issued.token.id
    assert mint["details"]["family_id"] == issued.family_id
    (row,) = _refresh_rows(box, issued.family_id)
    assert row["refresh_hash"] == values.digest(issued.refresh_token)
    assert row["access_token_id"] == issued.token.id
    assert row["redeemed_at"] is None and row["revoked"] is False

    again = tokens.exchange_code(
        box.backend,
        box.ledger,
        code=code,
        client_id=BROWSER,
        redirect_uri=REDIRECT,
        code_verifier=VERIFIER,
        owner=OWNER,
        now=T0,
    )
    assert again is None
    assert len(_events(box, "token.mint")) == 1
    assert len(box.backend.list_tokens()) == 1
    _assert_clean(box, code, session, issued.access_token, issued.refresh_token)


def test_a_wrong_verifier_spends_the_code_in_the_real_store(box: Box):
    session = sessions.establish(box.backend, now=T0)
    code = codes.issue(
        box.backend,
        client_id=BROWSER,
        redirect_uri=REDIRECT,
        code_challenge=pkce.s256(VERIFIER),
        session_hash=values.digest(session),
        grant=_code_grant(),
        now=T0,
    )
    for verifier in ("w" * 43, VERIFIER):  # the right verifier second: the code is already spent
        assert (
            tokens.exchange_code(
                box.backend,
                box.ledger,
                code=code,
                client_id=BROWSER,
                redirect_uri=REDIRECT,
                code_verifier=verifier,
                owner=OWNER,
                now=T0,
            )
            is None
        )
    assert _events(box, "token.mint") == [] and box.backend.list_tokens() == []
    _assert_clean(box, code, session)


# -- PKCE downgrades (§2, §5.3) -------------------------------------------------------------------


def _register_browser(box: Box) -> None:
    box.backend.put_client(
        ClientRegistration(
            client_id=BROWSER,
            client_name=BROWSER,
            client_type="browser",
            redirect_uris=[REDIRECT],
            registered_at="2026-10-01T09:00:00Z",
        )
    )


def _authorize(pkce_params: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [
        ("response_type", "code"),
        ("client_id", BROWSER),
        ("redirect_uri", REDIRECT),
        ("state", "s"),
        *pkce_params,
    ]


def _nothing_stored(box: Box) -> None:
    for table in ("as_codes", "as_decided", "as_refresh"):
        assert _read(box, f"SELECT COUNT(*) FROM {table}") == [(0,)], table
    assert box.backend.list_tokens() == [] and _events(box, "token.mint") == []


@pytest.mark.parametrize(
    ("pkce_params", "cause"),
    [
        ([("code_challenge", VERIFIER), ("code_challenge_method", "plain")], "missing_pkce"),
        ([("code_challenge", CHALLENGE)], "missing_pkce"),  # no method is no default
        ([("code_challenge", CHALLENGE), ("code_challenge_method", "s256")], "missing_pkce"),
        ([("code_challenge_method", "S256")], "missing_pkce"),
        ([("code_challenge", ""), ("code_challenge_method", "S256")], "missing_pkce"),
        ([("code_challenge", "short"), ("code_challenge_method", "S256")], "malformed"),
        ([("code_challenge", "+" * 43), ("code_challenge_method", "S256")], "malformed"),
    ],
    ids=["plain", "no-method", "lowercase-method", "no-challenge", "empty", "short", "alphabet"],
)
def test_a_pkce_downgrade_is_refused_at_pretrust_with_nothing_stored(
    box: Box, pkce_params: list[tuple[str, str]], cause: str
):
    _register_browser(box)
    session = sessions.establish(box.backend, now=T0)
    assert isinstance(
        gate.check(box.backend, box.ledger, session=session, authorization=None, query="", now=T0),
        gate.Session,
    )
    assert pretrust.admit(box.backend, box.ledger, _authorize(pkce_params)) is None
    (refused,) = _chain(box)
    assert refused["event"] == "authz.refuse" and refused["principal"] == "none"
    assert refused["details"] == {"cause": cause}
    _nothing_stored(box)
    _assert_clean(box, session, VERIFIER)


def test_the_s256_control_is_admitted_and_admission_stores_nothing(box: Box):
    _register_browser(box)
    params = [("code_challenge", pkce.s256(VERIFIER)), ("code_challenge_method", "S256")]
    admitted = pretrust.admit(box.backend, box.ledger, _authorize(params))
    assert admitted is not None and admitted.code_challenge == pkce.s256(VERIFIER)
    assert _chain(box) == []
    _nothing_stored(box)


@pytest.mark.parametrize(
    "verifier", [pkce.s256(VERIFIER), None, ""], ids=["challenge", "none", "empty"]
)
def test_a_plain_or_missing_verifier_spends_the_code_and_mints_nothing(box: Box, verifier):
    # Presenting the challenge itself is `plain`'s check, which this AS never runs (§2).
    session = sessions.establish(box.backend, now=T0)
    code = codes.issue(
        box.backend,
        client_id=BROWSER,
        redirect_uri=REDIRECT,
        code_challenge=pkce.s256(VERIFIER),
        session_hash=values.digest(session),
        grant=_code_grant(),
        now=T0,
    )
    assert _read(box, "SELECT COUNT(*) FROM as_codes") == [(1,)]
    for presented in (verifier, VERIFIER):  # the right verifier second: the code is already spent
        assert (
            tokens.exchange_code(
                box.backend,
                box.ledger,
                code=code,
                client_id=BROWSER,
                redirect_uri=REDIRECT,
                code_verifier=presented,
                owner=OWNER,
                now=T0,
            )
            is None
        )
    _nothing_stored(box)
    assert _chain(box) == []
    _assert_clean(box, code, session)


# -- refresh rotation and reuse (§9.2) -----------------------------------------------------------


def _revokes_by_token(box: Box) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in _events(box, "token.revoke"):
        counts[entry["subject"]] = counts.get(entry["subject"], 0) + 1
    return counts


def test_rotation_then_reuse_revokes_the_family_once_per_token(box: Box):
    first, code, session = _code_flow(box)
    second = tokens.refresh(
        box.backend, box.ledger, refresh_token=first.refresh_token, client_id=BROWSER, now=T0
    )
    assert second is not None and second.family_id == first.family_id
    assert second.token.owner == OWNER
    rows = {r["access_token_id"]: r for r in _refresh_rows(box, first.family_id)}
    assert set(rows) == {first.token.id, second.token.id}
    assert rows[first.token.id]["redeemed_at"] is not None
    assert rows[second.token.id]["redeemed_at"] is None
    assert [e["subject"] for e in _events(box, "token.mint")] == [first.token.id, second.token.id]
    assert _events(box, "token.revoke") == []

    replay = tokens.refresh(
        box.backend, box.ledger, refresh_token=first.refresh_token, client_id=BROWSER, now=T0
    )
    assert replay is None
    for token_id in (first.token.id, second.token.id):
        assert box.backend.get_token(token_id).revoked is True
    assert all(r["revoked"] for r in _refresh_rows(box, first.family_id))
    assert _revokes_by_token(box) == {first.token.id: 1, second.token.id: 1}
    assert {e["details"]["family_id"] for e in _events(box, "token.revoke")} == {first.family_id}

    # Replaying again, or presenting the newest value, writes nothing more (§9.2 "written once").
    for value in (first.refresh_token, second.refresh_token):
        assert tokens.refresh(
            box.backend, box.ledger, refresh_token=value, client_id=BROWSER, now=T0
        ) is None
    assert _revokes_by_token(box) == {first.token.id: 1, second.token.id: 1}
    assert len(_events(box, "token.mint")) == 2
    _assert_clean(
        box,
        code,
        session,
        first.access_token,
        first.refresh_token,
        second.access_token,
        second.refresh_token,
    )


def test_a_token_revoked_on_its_own_first_gets_no_second_revoke_on_reuse(box: Box):
    first, code, session = _code_flow(box)
    second = tokens.refresh(
        box.backend, box.ledger, refresh_token=first.refresh_token, client_id=BROWSER, now=T0
    )
    assert second is not None
    assert revoke.by_id(box.backend, box.ledger, token_id=first.token.id, viewer=OWNER) is True
    (own,) = _events(box, "token.revoke")
    assert own["subject"] == first.token.id
    assert own["details"] == {"family_id": first.family_id}

    assert tokens.refresh(
        box.backend, box.ledger, refresh_token=first.refresh_token, client_id=BROWSER, now=T0
    ) is None
    assert box.backend.get_token(first.token.id).revoked is True
    assert box.backend.get_token(second.token.id).revoked is True
    assert _revokes_by_token(box) == {first.token.id: 1, second.token.id: 1}
    _assert_clean(
        box,
        code,
        session,
        first.access_token,
        first.refresh_token,
        second.access_token,
        second.refresh_token,
    )


# -- the device flow (§3, §10.3, §11.8) ----------------------------------------------------------


def _token_request(box: Box, params: list[tuple[str, str]], now: datetime):
    return token_endpoint.respond(
        box.backend,
        box.ledger,
        params,
        content_type=FORM,
        authorization=None,
        owner=OWNER,
        now=now,
    )


def test_the_device_flow_against_the_real_store_mints_one_client_token(box: Box):
    box.backend.put_client(
        ClientRegistration(
            client_id=CLI,
            client_name=CLI,
            client_type="cli",
            redirect_uris=[],
            registered_at="2026-10-01T09:00:00Z",
        )
    )
    started = device_authorization.respond(
        box.backend,
        [("client_id", CLI), ("scope", "fetch node:*")],
        content_type=FORM,
        authorization=None,
        key=KEY,
        issuer=ISSUER,
        now=T0,
    )
    assert started.status == 200
    device_code, user_code = started.body["device_code"], started.body["user_code"]
    poll = [
        ("grant_type", token_endpoint.DEVICE_GRANT),
        ("device_code", device_code),
        ("client_id", CLI),
    ]
    pending = _token_request(box, poll, T0)
    assert pending.body == {"error": "authorization_pending"}

    record = device_entry.redeem(
        box.backend, box.ledger, key=KEY, user_code=user_code, now=T0 + timedelta(seconds=20)
    )
    assert record is not None and record["client_id"] == CLI
    # No session here: `decide` takes only `actor`, and binding the gate to the decision is the
    # router PR's (#208, #234), so a session established beside it would prove nothing.
    assert device_entry.decide(
        box.backend,
        box.ledger,
        key=KEY,
        user_code=user_code,
        approve=True,
        actor=OWNER,
        now=T0 + timedelta(seconds=30),
    )

    done = _token_request(box, poll, T0 + timedelta(seconds=40))
    assert done.status == 200, done.body
    (token,) = box.backend.list_tokens()
    assert token.principal == "client" and token.client == CLI and token.owner == OWNER
    assert (token.capabilities, token.scopes) == (["fetch"], ["*"])
    assert token.secret_hash == values.digest(done.body["access_token"])

    spent = _token_request(box, poll, T0 + timedelta(seconds=50))
    assert spent.body == {"error": "invalid_grant"}
    assert [e["subject"] for e in _events(box, "token.mint")] == [token.id]
    (redeemed,) = _events(box, "authz.redeem")
    assert redeemed["principal"] == "none" and redeemed["details"] == {"outcome": "found"}
    (granted,) = _events(box, "authz.grant")
    assert granted["principal"] == "interactive"
    assert granted["details"]["client_id"] == CLI and granted["details"]["decision"] == "granted"
    _assert_clean(
        box,
        device_code,
        user_code,
        values.normalize_user_code(user_code) or "",
        done.body["access_token"],
        done.body["refresh_token"],
    )


# -- the caller-less events (events.md §2, §12.2; #166) ------------------------------------------


def test_every_caller_less_emitter_on_main_appends_principal_none_and_only_it(box: Box):
    """#166: each `PRINCIPAL_NONE_EVENTS` member the AS emits is driven through the AS's own
    functions, not the ledger, and lands on the real chain with `principal: none`; every entry
    beside them names a caller. `authz.release` and `authz.tally` are the throttle's (#208) and
    `rest.tally` the REST door's: none has an emitter on `main` to drive yet."""
    _register_browser(box)
    box.backend.put_client(
        ClientRegistration(
            client_id=CLI,
            client_name=CLI,
            client_type="cli",
            redirect_uris=[],
            registered_at="2026-10-01T09:00:00Z",
        )
    )
    for credential in ("not-it", CONTAINER_SECRET):  # row (a): failed, then established
        login.attempt(
            box.backend, box.ledger, _Secret(), credential=credential, continue_value="/", now=T0
        )
    started = device_authorization.respond(
        box.backend,
        [("client_id", CLI), ("scope", "fetch")],
        content_type=FORM,
        authorization=None,
        key=KEY,
        issuer=ISSUER,
        now=T0,
    )
    user_code = started.body["user_code"]
    device_entry.redeem(box.backend, box.ledger, key=KEY, user_code="!!", now=T0)  # row (b)
    device_entry.redeem(box.backend, box.ledger, key=KEY, user_code=user_code, now=T0)
    device_entry.decide(
        box.backend, box.ledger, key=KEY, user_code=user_code, approve=True, actor=OWNER, now=T0
    )
    found = gate.check(
        box.backend, box.ledger, session=None, authorization="Bearer x", query="", now=T0
    )
    assert isinstance(found, gate.Refused)  # row (d) token_presented
    params = _authorize([("code_challenge", CHALLENGE), ("code_challenge_method", "S256")])
    assert pretrust.admit(box.backend, box.ledger, params[1:]) is None  # row (d) malformed
    admitted = pretrust.admit(box.backend, box.ledger, params)
    assert admitted is not None
    session = values.digest(sessions.establish(box.backend, now=T0))
    decided.record(box.backend, key=admitted.key, session_hash=session, decision="granted", now=T0)
    assert decided.first_replay(box.backend, box.ledger, session_hash=session, key=admitted.key)
    assert pretrust.admit(box.backend, box.ledger, params) is None  # row (d) replayed, keyed

    chain = _chain(box)
    caller_less = [e for e in chain if e["event"] in PRINCIPAL_NONE_EVENTS]
    assert {e["event"] for e in caller_less} == {"authz.login", "authz.redeem", "authz.refuse"}
    assert len(caller_less) == 2 + 2 + 4
    for entry in chain:
        assert (entry["principal"] == "none") == (entry["event"] in PRINCIPAL_NONE_EVENTS), entry
    for entry in caller_less:
        assert entry["actor"] in AS_THROTTLE_SURFACES and entry["subject"] is None
    causes = [e["details"]["cause"] for e in _events(box, "authz.refuse")]
    assert causes == ["token_presented", "malformed", "replayed", "replayed"]
    (granted,) = _events(box, "authz.grant")
    assert granted["principal"] == "interactive"
    _assert_clean(box, CONTAINER_SECRET, user_code, started.body["device_code"])
