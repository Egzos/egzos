# spec/contracts/

**Status: frozen at 0.3 (Chief, date of merge).** The freeze is the Chief's merge of the commit that
set this line, dated by that merge, after the Phase 0.3 review by A6 and the Chief personally.
a1p-planner prepared the text and did not declare it. From that merge, every document below is law.

## Index

Drafted in Phase 0.2 from the running walking skeleton (#25, #26–#30), with the Chief's freeze
decisions written in at 0.3 (#109). Each document's own status line reads the same as this one.

| document | what it fixes | status |
|---|---|---|
| [`context-item.md`](context-item.md) | the ContextItem schema: fields, `content`, `BlobGrant`, `provenance`, `lifecycle` | frozen at 0.3 |
| [`capabilities.md`](capabilities.md) | the six capabilities (`enterprise` omitted), role bundles, principals, tokens, coverage, human-only acts, silence-not-errors (§6) | frozen at 0.3 |
| [`events.md`](events.md) | the event taxonomy, approvals included; the entry shape and the hash chain | frozen at 0.3 |
| [`storage.md`](storage.md) | the backend contract, split by F3 into `ItemStore`, `ContainerState` and `BlobStore` | frozen at 0.3 |
| [`container.md`](container.md) | containers, addressing, the chain, serving policy, trust statuses, the gate, the config object | frozen at 0.3 |
| [`authorization-server.md`](authorization-server.md) | the container's OAuth 2.1 AS: auth-code + PKCE, device-code, MCP clients, client registration and the redirect allowlist (`egzos.io`, loopback), AS metadata | frozen at 0.3 |

The typed face of the set is `src/egzos/_types.py`. Every name there traces to a clause here, and
`tests/conformance/test_contract_tables.py` pins the vocabularies against these tables.

**Markings.** Clauses carry **running**, **decided, not running**, or `[0.3 · N]` — item `N` of the
Chief's freeze record on #31 (2026-10-03, with the revision of item 1 the same day).
`authorization-server.md` adds its own prose-derived markings (§K, a1p, `[LEAN]`). `[v1.1]` marks
what the record deferred to the Phase 5 boundary, with the reason. **No open→0.3 marking remains:**
the 45-item record answered all of them, so the collected list #30 asked for is the record itself.

## Interface rules the freeze honours

These rules from the decisions log (§N, §K) constrain what the frozen contracts may say:

- Signed-URL issuance passes Trust's capability check — artifact download IS fetch; blob pulls
  are separate audit events; Store/Vault never mints a URL on its own authority.
  (`context-item.md` §3, `events.md` §1 `blob.grant` / `blob.pull`)
- Writes land unverified; rules are served verified-only everywhere. (`container.md` §4–§5)
- Silence-not-errors — the API does not reveal what exists to a caller who cannot see it; no
  enumeration through error shapes. (`capabilities.md` §6, `storage.md` §5,
  `authorization-server.md` §5.3)
- PKCE mandatory for all public clients (browsers and the flagship). (`authorization-server.md` §2)
- AS metadata discovery is part of the frozen surface; any UI, ours or a fork's, authenticates
  to a container the same way. (`authorization-server.md` §6)

## After the freeze

`spec/contracts/**` is law. Changing a frozen contract is a `contract-change` escalation issue to
a1p-planner, batched at phase boundaries. Never change a frozen contract as a drive-by: file the
issue and take the next item.

**Contract v1.1 is planned at the Phase 5 boundary (R7):** the intelligence read surface and AS
metadata, plus every `[v1.1]` marking in the set. It is reviewed there by the Chief, a1p-planner and
a6-adversary, and is planned work, not a Phase 6 escalation.
