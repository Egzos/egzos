# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""GHSA-9gxm-mm8f-q49j: `egzos_remember` gives a principal without `fetch` the same answer for a
scope it covers as for one that does not exist (capabilities.md §6 clause 1, rest.md §3). The
request and the token are judged before the scope is looked up, and a refusal after the lookup is
the absent answer, with its probe."""

from __future__ import annotations

import asyncio
import json

import pytest

from egzos.container import OWNER, Container
from egzos.mcp.server import build_server

pytestmark = pytest.mark.adversarial

ABSENT = "01HZZZZZZZZZZZZZZZZZZZZZZZ"


def _remember(server, args):
    r = asyncio.run(server.call_tool("egzos_remember", args))
    return json.loads(r.content[0].text)


@pytest.mark.parametrize(("capabilities", "extra"), [(["organize"], {}),
                                                     (["remember"], {"kind": "zzz"})])
def test_a_covered_scope_answers_as_an_absent_one(tmp_path, capabilities, extra):
    c = Container(tmp_path / "home")
    owner = c.init()
    covered = c.nodes.create("project", "covered", c.nodes.user_root(), token=owner, actor=OWNER,
                             principal="interactive")
    token = c.auth.mint(principal="client", owner=OWNER, client="bot", role="reader",
                        scopes=["*"], actor=OWNER, by_principal="interactive")
    token.capabilities = capabilities  # covers everything, and may not read it
    c.backend.put_token(token)
    server = build_server(c, token)
    answers, traces = [], []
    for ref in (covered.id, "project:covered", ABSENT):
        before = len(c.ledger.tail(10_000))
        answers.append(_remember(server, {"text": "x", "scope": ref, **extra}))
        traces.append(len(c.ledger.tail(10_000)) - before)
    assert all(a == answers[-1] for a in answers) and answers[-1]["ok"] is False
    assert len(set(traces)) == 1  # a hit and a miss leave the same trace
