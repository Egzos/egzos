# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""U+0000 is kept only inside a document (storage.md §3.7), on every backend: a value a backend
stores or matches by outside one is refused with `ValueError` before any write, and a block the
refusal was raised in goes on. A search text matches documents, so it is not refused."""

from __future__ import annotations

import pytest

from egzos.model import ContextItem, Node, Token

AT = "2026-10-24T00:00:00Z"
NUL = "x\0"
NODE = Node(id=NUL, type="thread", name="n", parent=None, created_at=AT)
ITEM = ContextItem(id="i", kind="memory", scope=NUL, content={"body": "b"})
TOKEN = Token(id=NUL, principal="client", owner="self", client="bot", capabilities=["fetch"],
              scopes=["n1"], created_at=AT)
#: Each method that stores or matches by such a value, called with U+0000 in one of them.
CALLS = {
    "put_node": (NODE,), "get_node": (NUL,), "list_nodes": (None, NUL), "find_root": (NUL,),
    "put": (ITEM,), "get": (NUL,), "tombstone": (NUL,), "query": (["n", NUL],),
    "audit_append": ({"ts": AT, "hash": NUL, "prev_hash": "0" * 64},),
    "put_token": (TOKEN,), "get_token": (NUL,),
    "put_proposal": ({"id": "p", "status": NUL},), "get_proposal": (NUL,), "list_proposals": (NUL,),
    "throttle_incr": ("rest", NUL, "w"), "throttle_count": ("rest", "b", NUL),
    "throttle_buckets": ("rest", NUL), "throttle_windows": (NUL,), "throttle_forget": (NUL, "w"),
    "put_user_grant": ({"sub": NUL},), "get_user_grant": (NUL,),
    "put_agent_registration": ({"client_id": NUL, "sub": "s"},),
    "get_agent_registration": ("c", NUL), "list_agent_registrations": (NUL,),
    "put_config": (NUL, 1),
    "put_challenge": ({"id": "c", "expires_at": NUL},), "forget_challenges": (NUL,),
    "spend_challenge": (NUL,),
    "put_credential": ({"id": "c", "person": NUL},), "get_credential": (NUL,),
    "list_credentials": (NUL,),
    "put_upload": ({"id": NUL, "principal": "t"},), "get_upload": (NUL,), "list_uploads": (NUL,),
    "spend_upload": (NUL, "bytes"), "spend_grant": (NUL, AT), "forget_grants": (NUL,),
}
QUERIES = [{"key": NUL}, {"kinds": ["memory", NUL]}, {"statuses": [NUL]}]


def _everything(backend):
    return (backend.list_nodes(), backend.query(["n"], include_tombstoned=True),
            backend.audit_last(), backend.list_tokens(), backend.list_proposals(),
            backend.throttle_windows("rest"), backend.list_user_grants(),
            backend.list_agent_registrations(), backend.get_config(), backend.list_credentials(),
            backend.list_uploads())


@pytest.mark.parametrize("method", sorted(CALLS))
def test_a_value_holding_u0000_outside_a_document_is_refused_before_any_write(make_backend,
                                                                              method):
    backend, other = make_backend(), make_backend()
    backend.put(ContextItem(id="i", kind="memory", scope="n", content={"body": "b"}))
    before = _everything(other)
    with pytest.raises(ValueError, match="U\\+0000"):
        getattr(backend, method)(*CALLS[method])
    assert _everything(other) == before
    with backend.atomic():  # the refusal left nothing open, and wrote nothing a block undoes
        backend.put_config("after", 1)
    assert other.get_config() == {"after": 1}


@pytest.mark.parametrize("matched", QUERIES, ids=lambda q: next(iter(q)))
def test_a_query_matching_by_u0000_is_refused_but_a_search_text_is_not(backend, matched):
    item = ContextItem(id="i", kind="memory", scope="n", content={"body": "b\0c"})
    backend.put(item)
    with pytest.raises(ValueError):
        backend.query(["n"], **matched)
    assert backend.query(["n"], text="\0") == [item]  # sqlite's pattern ends at it: `%`
    assert backend.query(["n"], text="b") == [item] == [backend.get("i")]  # its document keeps it


def test_a_refusal_inside_a_block_spoils_nothing_and_the_block_goes_on(make_backend):
    backend, other = make_backend(), make_backend()
    with backend.atomic():
        backend.put_config("k", 1)
        with pytest.raises(ValueError):
            backend.put_config(NUL, 2)  # postgres `text` would abort the block; this never runs
        backend.put_config("j", 2)
    assert other.get_config() == {"k": 1, "j": 2}
