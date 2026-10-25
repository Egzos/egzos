# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""`ContainerState`'s nodes, tokens and proposals (storage.md §3) on every backend: each reads back
as put, a second put of one id replaces it (a move, a revocation, a decision), and a miss is `None`
or a shorter list (§5). No contract fixes a list's order, so ids are compared as sets."""

from __future__ import annotations

from dataclasses import replace

from egzos.model import Node, Token

AT = "2026-10-24T00:00:00Z"


def _node(nid, type, parent):
    return Node(id=nid, type=type, name=f"{type} {nid}", parent=parent, created_at=AT)


def _proposal(pid, status="open"):
    """As `Trust._park` writes one, with the wire key `from` (`_types.PROPOSAL_WIRE_KEY_FROM`)."""
    return {"id": pid, "status": status, "kind": "move", "items": ["i1"], "from": "n1", "to": "n2",
            "from_path": "inbox:inbox", "to_path": "team:t", "audience": [], "audience_delta": [],
            "blast_radius": 1, "manifest": "m", "reason": "", "created_at": AT,
            "proposed_by": {"actor": "bot", "principal": "client", "client": "bot"}}


def test_nodes_read_back_filter_on_parent_and_type_and_find_their_root(backend):
    nodes = [_node("u", "user", None), _node("g", "global", None), _node("i", "inbox", "u"),
             _node("t", "thread", "i")]
    for node in nodes:
        backend.put_node(node)
    assert backend.get_node("t") == nodes[3]
    assert backend.get_node("never") is None
    assert sorted(n.id for n in backend.list_nodes()) == ["g", "i", "t", "u"]
    assert [n.id for n in backend.list_nodes(parent="i")] == ["t"]
    assert [n.id for n in backend.list_nodes(type="inbox")] == ["i"]
    assert backend.list_nodes(parent="u", type="thread") == []
    assert backend.find_root("user") == nodes[0]
    assert backend.find_root("inbox") is None  # it has a parent: not a root
    backend.put_node(replace(nodes[3], parent="u"))  # a move is a metadata update
    assert backend.list_nodes(parent="i") == []
    assert backend.get_node("t").parent == "u"


def test_a_token_reads_back_with_its_secret_hash_and_a_revocation_replaces_it(backend):
    token = Token(id="t1", principal="client", owner="self", client="bot", capabilities=["fetch"],
                  scopes=["n1"], created_at=AT, secret_hash="ab" * 32)
    backend.put_token(token)
    assert backend.get_token("t1") == token  # `Auth.use` checks the hash it reads back
    backend.put_token(replace(token, revoked=True))
    assert backend.get_token("t1").revoked is True
    assert [t.id for t in backend.list_tokens()] == ["t1"]
    assert backend.get_token("never") is None


def test_proposals_read_back_list_by_status_and_a_decision_replaces_one(backend):
    backend.put_proposal(_proposal("p1"))
    backend.put_proposal(_proposal("p2"))
    executed = {**_proposal("p1", "executed"), "approved_by": "self", "executed_at": AT}
    backend.put_proposal(executed)
    assert backend.get_proposal("p1") == executed
    assert [p["id"] for p in backend.list_proposals("open")] == ["p2"]
    assert sorted(p["id"] for p in backend.list_proposals()) == ["p1", "p2"]
    assert backend.list_proposals("denied") == []
    assert backend.get_proposal("never") is None
