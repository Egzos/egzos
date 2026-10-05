# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
Walking-skeleton tests: one per shape 0.2 must read off the running code. Ugly is allowed;
these pin behaviour the contracts will freeze, so a1p can point at a test instead of prose.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from egzos.container import OWNER, Container
from egzos.model import ContextItem
from egzos.store.items import StoreError
from egzos.trust import HumanOnly, TrustError


@pytest.fixture()
def box(tmp_path: Path) -> Container:
    c = Container(tmp_path / "home")
    c.init()
    return c


def owner(c: Container):
    return c.auth.interactive_token()


# --- identity, capture, inbox ------------------------------------------------------------------
def test_init_creates_roots_inbox_and_interactive_admin_token(box: Container):
    assert box.nodes.user_root().type == "user"
    assert box.nodes.global_root().type == "global"
    assert box.nodes.inbox().parent == box.nodes.user_root().id
    t = owner(box)
    assert t.principal == "interactive" and t.has("admin") and t.scopes == ["*"]


def test_add_without_scope_lands_unverified_in_a_fresh_auto_titled_inbox_thread(box: Container):
    t = owner(box)
    item = box.store.add(
        body="Remember the milk\nand eggs", token=t, actor=OWNER, principal=t.principal
    )
    assert item.status == "unverified"
    assert item.content["auto_title"] == "Remember the milk"
    thread = box.backend.get_node(item.scope)
    assert thread.type == "thread" and thread.parent == box.nodes.inbox().id
    assert [i.id for _, i in box.store.inbox_items()] == [item.id]


def test_artifact_is_metadata_plus_content_addressed_blob(box: Container, tmp_path: Path):
    f = tmp_path / "notes.txt"
    f.write_text("hello blob")
    t = owner(box)
    item = box.store.add(file=f, token=t, actor=OWNER, principal=t.principal)
    assert item.kind == "artifact"
    assert item.content["sha256"] == box.blobs.digest(b"hello blob")
    assert box.blobs.get(item.content["sha256"]) == b"hello blob"
    # dedup by construction
    again = box.store.add(file=f, token=t, actor=OWNER, principal=t.principal)
    assert again.content["sha256"] == item.content["sha256"]


def test_unknown_fields_survive_round_trip(box: Container):
    d = {
        "id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "kind": "memory",
        "scope": box.nodes.inbox().id,
        "content": {"body": "x"},
        "someday_field": {"nested": True},
    }
    item = ContextItem.from_dict(d)
    box.backend.put(item)
    back = box.backend.get(item.id)
    assert back.to_dict()["someday_field"] == {"nested": True}


# --- ledger ---------------------------------------------------------------------------------------
def test_audit_is_hash_chained_append_only_and_detects_rewrites(box: Container):
    t = owner(box)
    box.store.add(body="a", token=t, actor=OWNER, principal=t.principal)
    assert box.ledger.verify()["ok"]
    db = sqlite3.connect(str(box.home / "egzos.db"))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE audit SET doc='{}' WHERE seq=1")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM audit WHERE seq=1")
    db.execute("DROP TRIGGER audit_no_update")
    row = json.loads(db.execute("SELECT doc FROM audit WHERE seq=2").fetchone()[0])
    row["details"]["type"] = "org"
    db.execute("UPDATE audit SET doc=? WHERE seq=2", (json.dumps(row),))
    db.commit()
    result = box.ledger.verify()
    assert result["ok"] is False and result["broken_at"] == 2


def test_reads_are_audited(box: Container):
    t = owner(box)
    box.resolver.resolve(box.nodes.user_root(), token=t, actor=OWNER)
    assert box.ledger.tail(1)[0]["event"] == "context.fetch"


# --- trust & serving ------------------------------------------------------------------------------
def test_rules_are_verified_only_at_every_scope_and_promotion_is_human_only(box: Container):
    t = owner(box)
    rule = box.store.add(
        body="never paste secrets", kind="rule", token=t, actor=OWNER, principal=t.principal
    )
    thread = box.backend.get_node(rule.scope)
    served = box.resolver.resolve(thread, token=t, actor=OWNER)
    assert [i["item"]["id"] for i in served["items"]] == [] and served["withheld"] == 1
    client = box.auth.mint(
        principal="client",
        owner=OWNER,
        client="bot",
        role="curator",
        scopes=["*"],
        actor=OWNER,
        by_principal="interactive",
    )
    with pytest.raises(HumanOnly):
        box.trust.promote(rule, token=client, actor="bot")
    box.trust.promote(rule, token=t, actor=OWNER)
    served = box.resolver.resolve(thread, token=t, actor=OWNER)
    assert [i["item"]["id"] for i in served["items"]] == [rule.id]
    assert box.backend.get(rule.id).provenance["approved_by"] == OWNER


def test_serving_policy_verified_only_from_team_outward_and_key_override(box: Container):
    t = owner(box)
    org = box.nodes.create(
        "org", "acme", box.nodes.user_root(), token=t, actor=OWNER, principal=t.principal
    )
    proj = box.nodes.create("project", "p", org, token=t, actor=OWNER, principal=t.principal)
    org_pref = box.store.add(
        body="tabs",
        kind="preference",
        key="indent",
        scope=org,
        token=t,
        actor=OWNER,
        principal=t.principal,
    )
    box.trust.promote(org_pref, token=t, actor=OWNER)
    proj_pref = box.store.add(
        body="spaces",
        kind="preference",
        key="indent",
        scope=proj,
        token=t,
        actor=OWNER,
        principal=t.principal,
    )
    r = box.resolver.resolve(proj, token=t, actor=OWNER, include_global=False)
    ids = [(i["item"]["id"], i["shadowed_by"]) for i in r["items"]]
    assert ids == [
        (proj_pref.id, None),
        (org_pref.id, proj_pref.id),
    ]  # most-specific-wins; chain visible
    assert [layer["policy"] for layer in r["chain"]] == [
        "serve-unverified",  # project
        "verified-only",  # org
        "verified-only",  # personal root (F4: reach → verification)
    ]


def test_gate_zero_delta_is_silent_nonzero_parks_and_manifest_binds(box: Container):
    t = owner(box)
    proj = box.nodes.create(
        "project", "p", box.nodes.user_root(), token=t, actor=OWNER, principal=t.principal
    )
    org = box.nodes.create(
        "org", "acme", box.nodes.user_root(), token=t, actor=OWNER, principal=t.principal
    )
    item = box.store.add(body="note", scope=proj, token=t, actor=OWNER, principal=t.principal)
    # solo: inward/outward alike, zero audience delta → instant, silently logged
    r = box.trust.move(item, org, token=t, actor=OWNER)
    assert r["moved"] and box.ledger.tail(1)[0]["event"] == "gate.pass.silent"
    # an agent that can see org → moving there widens the audience → parked
    box.auth.mint(
        principal="client",
        owner=OWNER,
        client="ops",
        role="operator",
        scopes=[org.id],
        actor=OWNER,
        by_principal="interactive",
    )
    item2 = box.store.add(body="note2", scope=proj, token=t, actor=OWNER, principal=t.principal)
    r = box.trust.move(item2, org, token=t, actor=OWNER)
    assert not r["moved"] and r["proposal"]["audience_delta"][0]["client"] == "ops"
    pid = r["proposal"]["id"]
    # TOCTOU: the audience changes before the yes → the approval no longer matches its manifest
    box.auth.mint(
        principal="client",
        owner=OWNER,
        client="late-joiner",
        role="reader",
        scopes=[org.id],
        actor=OWNER,
        by_principal="interactive",
    )
    with pytest.raises(TrustError):
        box.trust.execute(pid, token=t, actor=OWNER)
    assert box.backend.get_proposal(pid)["status"] == "stale"


def test_client_can_only_write_where_it_is_covered_and_silence_not_errors(box: Container):
    t = owner(box)
    org = box.nodes.create(
        "org", "acme", box.nodes.user_root(), token=t, actor=OWNER, principal=t.principal
    )
    client = box.auth.mint(
        principal="client",
        owner=OWNER,
        client="ops",
        role="contributor",
        scopes=[org.id],
        actor=OWNER,
        by_principal="interactive",
    )
    with pytest.raises(StoreError, match="scope not found"):
        box.store.add(body="into the inbox", token=client, actor="ops", principal="client")
    ok = box.store.add(
        body="into the org", scope=org, token=client, actor="ops", principal="client"
    )
    assert ok.scope == org.id
    # an uncovered layer is simply absent from the chain — never "access denied"
    r = box.resolver.resolve(org, token=client, actor="ops")
    assert [layer["type"] for layer in r["chain"]] == ["org"]


def test_quarantine_propagates_via_derived_from(box: Container):
    t = owner(box)
    a = box.store.add(body="src", token=t, actor=OWNER, principal=t.principal)
    b = box.store.add(body="copy", token=t, actor=OWNER, principal=t.principal)
    b.provenance["derived_from"] = a.id
    box.backend.put(b)
    affected = box.trust.quarantine(a, token=t, actor=OWNER, reason="poisoned")
    assert set(affected) == {a.id, b.id}
    assert box.backend.get(b.id).status == "quarantined"
