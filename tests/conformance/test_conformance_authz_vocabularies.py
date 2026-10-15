# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The authorization server's closed vocabularies, as they land in the real store and chain (#266).

`tests/_types/**` pins each closed tuple in `_types.py`, and each `authz` slice's unit tests pin
the words that slice writes, against a fake. Neither shows what a container holds once the real
modules have run against one `SqliteBackend` and its `Ledger`. Here one tour drives every path on
`main` that writes a closed word, and each test reads the words back from the chain or the store.

Two directions per vocabulary. Every word found is a member of its tuple, so nothing outside a
contract's closed set is ever written. And every member is found, except the ones named in
`UNREACHED` with the reason no path on `main` writes them, so a word cannot quietly stop being
written either. When #208 lands the throttle, its `throttled` causes leave `UNREACHED` and the tour
drives them.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, get_args

import pytest

from egzos._types import (
    AS_AUTHORIZE_POSTTRUST_CAUSES,
    AS_AUTHORIZE_PRETRUST_CAUSES,
    AS_CLIENT_REGISTER_OPS,
    AS_CLIENT_TYPES,
    AS_DEVICE_REDEMPTION_CAUSES,
    AS_GRANT_DECISIONS,
    AS_LOGIN_CAUSES,
    AS_REVOKE_REFUSAL_CAUSES,
    PRINCIPALS,
    TOKEN_PRINCIPALS,
    DeviceDecision,
)
from egzos.authz import (
    clients,
    decided,
    device_authorization,
    device_entry,
    gate,
    login,
    pkce,
    posttrust,
    pretrust,
    revoke,
    sessions,
    token_endpoint,
    values,
)
from egzos.backends.sqlite import SqliteBackend
from egzos.ledger import Ledger
from egzos.model import Token

T0 = datetime(2026, 10, 15, 9, 0, 0, tzinfo=UTC)
OWNER = "owner"
REDIRECT = "https://egzos.io/connect/callback"
CHALLENGE = pkce.s256("v" * 43)
FORM = "application/x-www-form-urlencoded"
KEY = b"k" * 32  # a fixture device-code key; provisioning the real one is #143's
ADMIN = Token(
    id="tok-owner",
    principal="interactive",
    owner=OWNER,
    client="egzos-cli",
    capabilities=["admin"],
    scopes=["*"],
)

#: `details.cause` per event, and its closed tuple.
CAUSES: dict[str, tuple[str, ...]] = {
    "authz.login": AS_LOGIN_CAUSES,
    "authz.redeem": AS_DEVICE_REDEMPTION_CAUSES,
    "authz.refuse": AS_AUTHORIZE_PRETRUST_CAUSES,
    "authz.reject": AS_AUTHORIZE_POSTTRUST_CAUSES,
    "authz.revoke_refuse": AS_REVOKE_REFUSAL_CAUSES,
}

#: The members no path on `main` writes, and why. Nothing else may be missing from the tour.
UNREACHED: dict[str, set[str]] = {
    "authz.login": {"throttled", "unknown"},  # #208; v1.0's login takes no user id (§11.7)
    "authz.redeem": {"throttled"},  # #208
    "authz.refuse": {"throttled"},  # #208
    "authz.reject": set(),
    "authz.revoke_refuse": {"throttled"},  # #208
}


class _Secret:
    def verify(self, presented: str) -> bool:
        return presented == "the-container-secret"


def _authorize(client_id: str, redirect: str, **extra: str) -> list[tuple[str, str]]:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect,
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
        **extra,
    }
    return list(params.items())


def _device(box: SqliteBackend, client_id: str, now: datetime) -> dict[str, Any]:
    started = device_authorization.respond(
        box,
        [("client_id", client_id), ("scope", "fetch")],
        content_type=FORM,
        authorization=None,
        key=KEY,
        issuer="https://box.example/",
        now=now,
    )
    assert started.status == 200
    return started.body


def _tour(box: SqliteBackend, ledger: Ledger) -> None:
    """Every path on `main` that writes a closed word, each reached once at least."""
    browser = clients.register(
        box,
        ledger,
        token=ADMIN,
        actor=OWNER,
        client_name="web",
        client_type="browser",
        redirect_uris=[REDIRECT],
        now=T0,
    )
    cli = clients.register(
        box,
        ledger,
        token=ADMIN,
        actor=OWNER,
        client_name="cli",
        client_type="cli",
        redirect_uris=[],
        now=T0,
    )
    gone = clients.register(
        box,
        ledger,
        token=ADMIN,
        actor=OWNER,
        client_name="mcp",
        client_type="mcp",
        redirect_uris=[],
        now=T0,
    )
    clients.amend(
        box, ledger, token=ADMIN, actor=OWNER, client_id=cli["client_id"], client_name="c"
    )
    clients.remove(box, ledger, token=ADMIN, actor=OWNER, client_id=gone["client_id"])

    for credential in ("wrong", "the-container-secret"):
        login.attempt(box, ledger, _Secret(), credential=credential, continue_value="/", now=T0)

    # Row (b): malformed, invalid, found, used (after a decision), expired. `held` is approved
    # and never polled, so the store keeps a `granted` row beside the `denied` and `pending` ones.
    approved, held, denied, stale = (_device(box, cli["client_id"], T0) for _ in range(4))
    for user_code in ("!!", "BCDF-BCDF", approved["user_code"]):
        device_entry.redeem(box, ledger, key=KEY, user_code=user_code, now=T0)
    for body, approve in ((approved, True), (held, True), (denied, False)):
        assert device_entry.decide(
            box, ledger, key=KEY, user_code=body["user_code"], approve=approve, actor=OWNER, now=T0
        )
    device_entry.redeem(box, ledger, key=KEY, user_code=approved["user_code"], now=T0)
    late = T0 + timedelta(hours=1)
    device_entry.redeem(box, ledger, key=KEY, user_code=stale["user_code"], now=late)
    poll = [("grant_type", token_endpoint.DEVICE_GRANT), ("device_code", approved["device_code"])]
    minted = token_endpoint.respond(
        box,
        ledger,
        [*poll, ("client_id", cli["client_id"])],
        content_type=FORM,
        authorization=None,
        owner=OWNER,
        now=T0 + timedelta(seconds=10),
    )
    assert minted.status == 200, minted.body

    # Row (d): every pre-trust cause but `throttled`, in §5.3's order.
    assert isinstance(
        gate.check(box, ledger, session=None, authorization="Bearer x", query="", now=T0),
        gate.Refused,
    )
    good = _authorize(browser["client_id"], REDIRECT, state="s", scope="fetch")
    for refused in (
        _authorize(browser["client_id"], REDIRECT, response_type="token"),
        _authorize("no-such-client", REDIRECT),
        _authorize(browser["client_id"], "https://elsewhere.example/cb"),
        _authorize(browser["client_id"], REDIRECT, code_challenge_method="plain"),
    ):
        assert pretrust.admit(box, ledger, refused) is None
    admitted = pretrust.admit(box, ledger, good)
    assert admitted is not None
    session = values.digest(sessions.establish(box, now=T0))
    for decision in AS_GRANT_DECISIONS:  # the decided store holds both words
        key = f"{decision}-{admitted.key}"
        decided.record(box, key=key, session_hash=session, decision=decision, now=T0)
    decided.record(box, key=admitted.key, session_hash=session, decision="granted", now=T0)
    assert pretrust.admit(box, ledger, good) is None

    # Row (f): both post-trust causes, and the render beside them.
    for scope, reaches in (("bogus", True), ("node:n1", False), ("fetch", True)):
        offered = pretrust.admit(
            box, ledger, _authorize(browser["client_id"], REDIRECT, scope=scope)
        )
        assert offered is not None
        posttrust.judge(offered, ledger, actor=OWNER, reaches=lambda _node, r=reaches: r)

    # §11.9: both revoke refusals on the owner's page.
    (token,) = box.list_tokens()
    revoke.by_id(box, ledger, token_id="no-such-token", viewer=OWNER)
    revoke.by_id(box, ledger, token_id=token.id, viewer="someone-else")


@pytest.fixture(scope="module")
def toured(tmp_path_factory: pytest.TempPathFactory) -> tuple[SqliteBackend, list[dict[str, Any]]]:
    path: Path = tmp_path_factory.mktemp("vocab") / "container.db"
    box = SqliteBackend(path)
    ledger = Ledger(box)
    _tour(box, ledger)
    assert ledger.verify()["ok"] is True
    return box, list(box.audit_iter())


def _found(chain: list[dict[str, Any]], event: str, field: str) -> set[str]:
    return {e["details"][field] for e in chain if e["event"] == event and field in e["details"]}


def _column(box: SqliteBackend, table: str) -> list[dict[str, Any]]:
    # Beneath `ASState` on purpose: it has no listing read. The table names are the store's
    # layout as of #265, so a rename fails loudly here.
    with closing(sqlite3.connect(f"file:{box.path}?mode=ro", uri=True)) as db:
        return [json.loads(doc) for (doc,) in db.execute(f"SELECT doc FROM {table}")]


@pytest.mark.parametrize("event", sorted(CAUSES))
def test_every_cause_written_is_closed_and_every_reachable_one_is_written(toured, event: str):
    _, chain = toured
    found = _found(chain, event, "cause")
    assert found <= set(CAUSES[event]), found - set(CAUSES[event])
    assert UNREACHED[event] <= set(CAUSES[event])
    assert found == set(CAUSES[event]) - UNREACHED[event]


def test_grant_decisions_and_register_ops_are_closed_and_all_written(toured):
    _, chain = toured
    assert _found(chain, "authz.grant", "decision") == set(AS_GRANT_DECISIONS)
    assert _found(chain, "client.register", "op") == set(AS_CLIENT_REGISTER_OPS)


def test_every_entry_names_a_closed_principal(toured):
    _, chain = toured
    assert chain and {e["principal"] for e in chain} == set(PRINCIPALS)


def test_the_store_reads_back_only_closed_words(toured):
    box, _ = toured
    types = {c["client_type"] for c in _column(box, "as_clients")}
    assert types == set(AS_CLIENT_TYPES) - {"mcp"}  # the `mcp` entry was removed
    assert {r["decision"] for r in _column(box, "as_decided")} == set(AS_GRANT_DECISIONS)
    assert {r["decision"] for r in _column(box, "as_devices")} == set(get_args(DeviceDecision))
    principals = {t.principal for t in box.list_tokens()}
    assert principals == {"client"} and principals <= set(TOKEN_PRINCIPALS)
