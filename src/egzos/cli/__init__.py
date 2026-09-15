# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The CLI — first surface, doubles as the test harness (v0.3 §10). Daily one-worders: login, fetch,
add, ls, serve, find; noun-verb for the rest; --json everywhere; sticky scope (v0.4 §9).

Walking skeleton verbs: init · whoami · add · ls · fetch · find · cd · pwd · mk · mv · trust
(pending / approve / deny / quarantine) · token (create / ls) · audit (tail / verify) · serve --mcp.
`%n` handles act on the numbered results of the last `find` and resolve to real ids underneath.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import typer

from egzos.container import OWNER, Container
from egzos.model import Node
from egzos.store.items import StoreError
from egzos.store.nodes import StructureError
from egzos.trust import TrustError

app = typer.Typer(
    add_completion=False, no_args_is_help=False, help="egzos — your context, your container."
)
trust_app = typer.Typer(help="Trust: pending queue, promotion, quarantine.")
audit_app = typer.Typer(help="Audit: the hash-chained ledger.")
token_app = typer.Typer(help="Tokens: client principals and their capabilities.")
app.add_typer(trust_app, name="trust")
app.add_typer(audit_app, name="audit")
app.add_typer(token_app, name="token")

_state: dict[str, Any] = {"json": False}


# -- helpers -----------------------------------------------------------------------------------
def _out(payload: Any, human: str | None = None) -> None:
    if _state["json"]:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    elif human is not None:
        typer.echo(human)


def _fail(msg: str, code: int = 1) -> None:
    _out({"error": msg}, msg)
    raise typer.Exit(code)


def _container() -> Container:
    return Container()


def _scope_file() -> Path:
    return Path.cwd() / ".egzos"


def _sticky_scope(c: Container) -> Node | None:
    """Sticky scope per shell/project: the `.egzos` file in the working directory (v0.3 §4)."""
    f = _scope_file()
    if f.exists():
        return c.nodes.resolve_ref(f.read_text().strip())
    return None


def _scope_or(c: Container, ref: str | None, default: Node | None) -> Node | None:
    if ref:
        node = c.nodes.resolve_ref(ref)
        if not node:
            _fail("scope not found")
        return node
    return _sticky_scope(c) or default


def _item_ref(c: Container, ref: str):
    """Exact ids for machines, `%n` for humans (v0.3 §4); `%n` resolves to the real id."""
    if ref.startswith("%"):
        f = c.home / "last-find.json"
        if not f.exists():
            _fail("no previous `find` to take %n from")
        mapping = json.loads(f.read_text())
        real = mapping.get(ref[1:])
        if not real:
            _fail(f"{ref} is not in the last find")
        ref = real
    item = c.store.get(ref)
    if not item:
        _fail(
            "not found"
        )  # silence-not-errors: the same answer whether it exists or is out of scope
    return item


def _p(c: Container, node_id: str) -> str:
    node = c.backend.get_node(node_id)
    return c.nodes.path(node) if node else node_id


@app.callback()
def _root(
    json_: bool = typer.Option(False, "--json", help="Machine-readable output on every command."),
):
    _state["json"] = json_


# -- init / whoami ------------------------------------------------------------------------
@app.command()
def init():
    """Create the container: roots, inbox, the owner's interactive token."""
    c = _container()
    token = c.init()
    roots = {
        "user": c.nodes.path(c.nodes.user_root()),
        "global": c.nodes.path(c.nodes.global_root()),
    }
    _out(
        {"home": str(c.home), "roots": roots, "token": token.id},
        f"container at {c.home}\nroots: {roots['user']}  ·  {roots['global']}  ·  "
        "inbox under user:self\n"
        f"interactive token {token.id[:8]}… in the keychain stand-in ({c.home / 'keychain.json'})",
    )


@app.command()
def whoami():
    """Which principal and capabilities this shell holds."""
    c = _container()
    token = c.require_token()
    _out(
        token.to_dict(),
        f"{token.owner} · principal={token.principal} · client={token.client} · "
        f"capabilities={','.join(token.capabilities)} · scopes={','.join(token.scopes)}",
    )


# -- capture ------------------------------------------------------------------------------
@app.command()
def add(
    what: str = typer.Argument(
        ..., help="Text to remember, ./file for an artifact, or - for stdin."
    ),
    kind: str | None = typer.Option(None, "--kind", "-k"),
    key: str | None = typer.Option(None, "--key", help="Enables cross-scope override."),
    tag: list[str] = typer.Option([], "--tag", "-t"),
    scope: str | None = typer.Option(
        None, "--scope", "-s", help="Node id or path; default: inbox."
    ),
):
    """Capture. No scope → the inbox, in a fresh auto-titled thread. Lands unverified."""
    c = _container()
    token = c.require_token()
    node = _scope_or(c, scope, None)
    body: str | None = None
    file: Path | None = None
    if what == "-":
        body = sys.stdin.read()
    elif Path(what).is_file():
        file = Path(what)
    else:
        body = what
    try:
        item = c.store.add(
            body=body,
            file=file,
            kind=kind,
            scope=node,
            key=key,
            tags=tag,
            token=token,
            actor=OWNER,
            principal=token.principal,
        )
    except StoreError as e:
        _fail(str(e))
    _out(
        item.to_dict(),
        f"{item.id}  {item.kind:<10} unverified  {_p(c, item.scope)}\n"
        f"  “{item.content['auto_title']}”",
    )


@app.command()
def ls(
    inbox: bool = typer.Option(
        False, "--inbox", help="The incoming bucket (default when no scope)."
    ),
    scope: str | None = typer.Option(None, "--scope", "-s"),
):
    """List items. `ls --inbox` is the capture queue."""
    c = _container()
    c.require_token()
    node = _scope_or(c, scope, None)
    if node and not inbox:
        rows = [(node, i) for i in c.backend.query([node.id])]
    else:
        rows = c.store.inbox_items()
    _out(
        [{"scope": c.nodes.path(n), **i.to_dict()} for n, i in rows],
        "\n".join(
            f"{i.id}  {i.kind:<10} {i.status:<10} {c.nodes.path(n)}  "
            f"“{i.content.get('auto_title', '')}”"
            for n, i in rows
        )
        or "(empty)",
    )


# -- resolve --------------------------------------------------------------------------------
@app.command()
def fetch(
    scope: str | None = typer.Argument(
        None, help="Node id or path; default: sticky scope, then user:self."
    ),
    kind: list[str] = typer.Option([], "--kind", "-k"),
    key: str | None = typer.Option(None, "--key"),
    no_global: bool = typer.Option(False, "--no-global"),
):
    """Read merged context for a scope: the chain, innermost first, most-specific-wins."""
    c = _container()
    token = c.require_token()
    node = _scope_or(c, scope, c.nodes.user_root())
    r = c.resolver.resolve(
        node, token=token, actor=OWNER, kinds=kind or None, key=key, include_global=not no_global
    )
    lines = [
        f"scope {r['scope']}",
        "chain: " + " → ".join(f"{layer['path']} [{layer['policy']}]" for layer in r["chain"]),
    ]
    for e in r["items"]:
        it = e["item"]
        flag = f"  (shadowed by {e['shadowed_by'][:8]}…)" if e["shadowed_by"] else ""
        keyf = f" key={it['key']}" if it.get("key") else ""
        lines.append(
            f"  {it['id']}  {it['kind']:<10} {e['trust']:<10} @{e['layer']}{keyf}{flag}\n"
            f"      “{it['content'].get('auto_title', '')}”"
        )
    if r["withheld"]:
        lines.append(f"  ({r['withheld']} item(s) not served under the layer policies)")
    _out(r, "\n".join(lines))


@app.command()
def find(
    description: str = typer.Argument(...), kind: list[str] = typer.Option([], "--kind", "-k")
):
    """Numbered results across every kind/scope the token sees, recency-ranked; act with %n."""
    c = _container()
    token = c.require_token()
    covered = [n for n in c.backend.list_nodes() if c.trust.covers(token, n)]
    hits = []
    for n in covered:
        for item in c.backend.query([n.id], kinds=kind or None, text=description):
            # fetch serves under policy; find is the curation view — the interactive curator sees
            # every covered item with its trust label (labels + promotion queue are the control).
            curator = token.principal == "interactive" and token.has("curate")
            if item.status != "quarantined" and (curator or c.resolver.serve(item, n)):
                hits.append((n, item))
    hits.sort(key=lambda t: t[1].lifecycle.get("updated_at", ""), reverse=True)
    mapping = {str(i + 1): item.id for i, (_, item) in enumerate(hits)}
    (c.home / "last-find.json").write_text(json.dumps(mapping))
    c.ledger.append(
        "context.fetch",
        actor=OWNER,
        principal=token.principal,
        subject=None,
        scope=None,
        client=token.client,
        query=description,
        items=list(mapping.values()),
        layers=[],
        withheld=0,
    )
    _out(
        [
            {"n": i + 1, "scope": c.nodes.path(n), **item.to_dict()}
            for i, (n, item) in enumerate(hits)
        ],
        "\n".join(
            f"%{i + 1:<3} {item.kind:<10} {item.status:<10} {c.nodes.path(n)}  "
            f"“{item.content.get('auto_title', '')}”"
            for i, (n, item) in enumerate(hits)
        )
        or "(no matches)",
    )


# -- scope ------------------------------------------------------------------------------------
@app.command()
def cd(
    scope: str = typer.Argument(
        ..., help="Node id or path — makes it the sticky scope for this directory."
    ),
):
    """Sticky scope: writes `.egzos` in the working directory (alias for `scope use`)."""
    c = _container()
    c.require_token()
    node = c.nodes.resolve_ref(scope)
    if not node:
        _fail("scope not found")
    _scope_file().write_text(node.id)
    _out({"scope": node.id, "path": c.nodes.path(node)}, c.nodes.path(node))


@app.command()
def pwd():
    """The sticky scope, if any."""
    c = _container()
    c.require_token()
    node = _sticky_scope(c)
    _out(
        {"scope": node.id if node else None, "path": c.nodes.path(node) if node else None},
        c.nodes.path(node) if node else "(no sticky scope — inbox)",
    )


@app.command()
def mk(
    type: str = typer.Argument(..., help="thread | project | team | org | exo"),
    name: str = typer.Argument(...),
    parent: str | None = typer.Option(
        None, "--in", help="Parent node; default: sticky scope, then user:self."
    ),
):
    """Create a container (SKELETON verb — the log says only 'creating wrappers is free')."""
    c = _container()
    token = c.require_token()
    p = _scope_or(c, parent, c.nodes.user_root())
    try:
        node = c.nodes.create(type, name, p, token=token, actor=OWNER, principal=token.principal)
    except StructureError as e:
        _fail(str(e))
    _out(node.to_dict(), f"{node.id}  {c.nodes.path(node)}")


@app.command()
def mv(
    item: str = typer.Argument(..., help="Item id or %n"),
    to: str = typer.Argument(..., help="Target scope"),
):
    """Move an item. Inward = instant. Outward = the gate: resolved audience, then a human yes."""
    c = _container()
    token = c.require_token()
    it = _item_ref(c, item)
    target = c.nodes.resolve_ref(to)
    if not target:
        _fail("scope not found")
    try:
        r = c.trust.move(it, target, token=token, actor=OWNER)
    except TrustError as e:
        _fail(str(e))
    if r["moved"]:
        _out(r, f"moved → {c.nodes.path(target)}  (audience delta: none — silent gate pass logged)")
    else:
        p = r["proposal"]
        who = ", ".join(
            f"{a['client']} ({a['role']}, {a['principal']})" for a in p["audience_delta"]
        )
        _out(
            r,
            f"GATE — this move widens the audience.\n  {p['from_path']}  →  {p['to_path']}\n"
            f"  new audience: {who}\n"
            f"  inheritance: {p['blast_radius']} container(s) under the target inherit it\n"
            f"  parked as proposal {p['id']}  ·  `egzos trust approve {p['id']}` to confirm",
        )


# -- trust ------------------------------------------------------------------------------------
@trust_app.command("pending")
def trust_pending():
    """Unverified items awaiting promotion, and open proposals awaiting a human yes."""
    c = _container()
    c.require_token()
    pend = c.trust.pending()
    lines = ["items awaiting promotion:"] + [
        f"  {i.id}  {i.kind:<10} @{_p(c, i.scope)}  “{i.content.get('auto_title', '')}”"
        f"  by {i.provenance.get('client')}"
        for i in pend["items"]
    ] or []
    lines.append("open proposals:")
    lines += [
        f"  {p['id']}  move {len(p['items'])} item(s) {p['from_path']} → {p['to_path']}  widens to "
        f"{', '.join(a['client'] for a in p['audience_delta'])}  ({p['reason']})"
        for p in pend["proposals"]
    ] or ["  (none)"]
    _out(
        {"items": [i.to_dict() for i in pend["items"]], "proposals": pend["proposals"]},
        "\n".join(lines),
    )


@trust_app.command("approve")
def trust_approve(ref: str = typer.Argument(..., help="Item id, %n, or proposal id")):
    """Human-only: promote an item to verified, or execute a parked proposal (manifest-bound)."""
    c = _container()
    token = c.require_token()
    try:
        if c.backend.get_proposal(ref):
            p = c.trust.execute(ref, token=token, actor=OWNER)
            _out(
                p,
                f"executed proposal {p['id']} → {p['to_path']}  "
                f"(manifest {p['manifest'][:12]}… matched)",
            )
            return
        item = _item_ref(c, ref)
        item = c.trust.promote(item, token=token, actor=OWNER)
        _out(
            item.to_dict(),
            f"{item.id} → verified  (approved_by {item.provenance['approved_by']}, "
            f"manifest {item.trust['manifest'][:12]}…)",
        )
    except TrustError as e:
        _fail(str(e))


@trust_app.command("deny")
def trust_deny(proposal: str):
    c = _container()
    token = c.require_token()
    try:
        p = c.trust.deny(proposal, token=token, actor=OWNER)
    except TrustError as e:
        _fail(str(e))
    _out(p, f"denied {p['id']}")


@trust_app.command("quarantine")
def trust_quarantine(item: str, reason: str = typer.Option(..., "--reason")):
    """Curate: stop serving an item and everything derived from it, immediately."""
    c = _container()
    token = c.require_token()
    it = _item_ref(c, item)
    try:
        affected = c.trust.quarantine(it, token=token, actor=OWNER, reason=reason)
    except TrustError as e:
        _fail(str(e))
    _out({"affected": affected}, f"quarantined {len(affected)} item(s): {', '.join(affected)}")


# -- tokens ------------------------------------------------------------------------------------
@token_app.command("create")
def token_create(
    client: str = typer.Option(..., "--client"),
    role: str = typer.Option(
        "contributor", "--role", help="reader|contributor|operator|curator|admin"
    ),
    scope: list[str] = typer.Option(
        [], "--scope", help="Node ids/paths covered; default: user:self"
    ),
):
    """Mint a CLIENT principal for a machine client. Machine clients never touch web auth."""
    c = _container()
    token = c.require_token()
    if not token.has("admin"):
        _fail("token create needs `admin`")
    if role == "admin":
        typer.echo(
            "warning: admin for an agent — it can mint itself anything (--i-understand in v0.1)",
            err=True,
        )
    scopes = []
    for ref in scope or ["user:self"]:
        if ref == "*":
            scopes.append("*")
            continue
        n = c.nodes.resolve_ref(ref)
        if not n:
            _fail(f"scope not found: {ref}")
        scopes.append(n.id)
    t = c.auth.mint(
        principal="client",
        owner=OWNER,
        client=client,
        role=role,
        scopes=scopes,
        actor=OWNER,
        by_principal=token.principal,
    )
    _out(
        t.to_dict(),
        f"{t.id}\n  client={client} principal=client role={role} "
        f"scopes={','.join(_p(c, s) if s != '*' else '*' for s in scopes)}\n"
        f"  export EGZOS_TOKEN={t.id}   # hand this to the client; never to a human shell",
    )


@token_app.command("ls")
def token_ls():
    c = _container()
    c.require_token()
    ts = c.backend.list_tokens()
    _out(
        [t.to_dict() for t in ts],
        "\n".join(
            f"{t.id}  {t.principal:<11} {t.client:<14} {','.join(t.capabilities):<45} "
            f"last_used={t.last_used or '-'}"
            f"{'  REVOKED' if t.revoked else ''}"
            for t in ts
        ),
    )


# -- audit ------------------------------------------------------------------------------------
@audit_app.command("tail")
def audit_tail(n: int = typer.Option(20, "-n")):
    """The last n audit entries — reads included."""
    c = _container()
    c.require_token()
    entries = c.ledger.tail(n)
    _out(
        entries,
        "\n".join(
            f"{e['seq']:>5}  {e['ts']}  {e['event']:<18} {e['principal']:<11} "
            f"{(e.get('subject') or '-')[:26]:<26} "
            f"{json.dumps(e.get('details') or {}, ensure_ascii=False)[:70]}"
            for e in entries
        )
        or "(empty)",
    )


@audit_app.command("verify")
def audit_verify():
    """Walk the hash chain from genesis. Exit 1 if it is broken."""
    c = _container()
    c.require_token()
    result = c.ledger.verify()
    _out(
        result,
        (
            f"chain ok · {result['entries']} entries · head {result['head'][:16]}…"
            if result["ok"]
            else f"CHAIN BROKEN at seq {result['broken_at']}: {result['reason']}"
        ),
    )
    if not result["ok"]:
        raise typer.Exit(1)


# -- serve ------------------------------------------------------------------------------------
@app.command()
def serve(
    mcp: bool = typer.Option(False, "--mcp", help="Speak MCP over stdio."),
    token: str | None = typer.Option(
        None, "--token", help="Client token id; default: $EGZOS_TOKEN"
    ),
):
    """Open the door. Runs as the CLIENT principal it was started with — never as you."""
    if not mcp:
        _fail("only --mcp (stdio) exists in the skeleton; REST/TLS arrive in Phase 2/5")
    c = _container()
    tid = token or os.environ.get("EGZOS_TOKEN")
    if not tid:
        _fail(
            "serve needs a client token: `egzos token create --client <name>` "
            "then --token / EGZOS_TOKEN",
            2,
        )
    t = c.auth.use(tid)
    if not t:
        _fail("token unknown or revoked", 2)
    if t.principal == "interactive":
        _fail(
            "refusing to serve on an interactive token — agents never hold the human's principal", 2
        )
    from egzos.mcp.server import serve_stdio

    serve_stdio(c, t)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an exit code (tests call main([]))."""
    args = sys.argv[1:] if argv is None else argv
    try:
        rv = app(args=args or ["--help"], standalone_mode=False)
        return int(rv) if isinstance(rv, int) else 0
    except typer.Exit as e:
        return int(e.exit_code)
    except SystemExit as e:
        return int(e.code or 0)
    except PermissionError as e:
        typer.echo(str(e), err=True)
        return 2
