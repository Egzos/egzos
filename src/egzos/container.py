# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The container — the user's home (v0.4 §1). One process-local assembly of backend, ledger, nodes,
store, blobs and auth rooted at EGZOS_HOME (default ~/.egzos). The container is the availability
boundary (v0.4 §16): nothing else can serve what it can't.
"""

from __future__ import annotations

import os
from pathlib import Path

from egzos.auth import Auth
from egzos.backends import SqliteBackend
from egzos.ledger import Ledger
from egzos.model import Token
from egzos.resolver import Resolver
from egzos.store import BlobStore, NodeService, Store
from egzos.trust import TrustEngine

OWNER = "self"


def default_home() -> Path:
    return Path(os.environ.get("EGZOS_HOME", Path.home() / ".egzos"))


class Container:
    def __init__(self, home: Path | None = None):
        self.home = Path(home or default_home())
        # The database holds the chain, every item and the token hashes: the owner's only. Created
        # 0700 (no window at the umask's mode), then pinned 0700 if it already existed.
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.home, 0o700)
        self.backend = SqliteBackend(self.home / "egzos.db")
        self.ledger = Ledger(self.backend)
        self.nodes = NodeService(self.backend, self.ledger)
        self.blobs = BlobStore(self.home / "blobs")
        self.store = Store(self.backend, self.ledger, self.nodes, self.blobs)
        self.auth = Auth(self.home, self.backend, self.ledger)
        self.trust = TrustEngine(self.backend, self.ledger, self.nodes)
        self.resolver = Resolver(self.backend, self.ledger, self.nodes, self.trust)
        self.store.covers = self.trust.covers
        self.nodes.covers = self.trust.covers

    @property
    def initialized(self) -> bool:
        return self.backend.find_root("user") is not None

    def init(self) -> Token:
        """Create the roots and the owner's interactive token; put it in the keychain stand-in.
        `login` (device-code) replaces this step from Phase 2; the skeleton is single-user."""
        if self.initialized:
            token = self.auth.interactive_token()
            if token and token.principal == "interactive":
                return token
            if token:
                raise PermissionError(
                    "this container is already initialized and the token presented is a client "
                    "principal's; init answers only for the owner"
                )
            # Never mint a second owner, and never overwrite the keychain, because a token did
            # not resolve: that is exactly what a wrong or revoked EGZOS_TOKEN looks like.
            raise PermissionError(
                "this container is already initialized and the token presented does not resolve; "
                "unset EGZOS_TOKEN or restore the keychain — init will not mint a new owner"
            )
        self.ledger.append(
            "container.init", actor=OWNER, principal="interactive", home=str(self.home)
        )
        self.nodes.ensure_roots(actor=OWNER, principal="interactive")
        token = self.auth.mint(
            principal="interactive",
            owner=OWNER,
            client="cli",
            role="admin",
            scopes=["*"],
            actor=OWNER,
            by_principal="interactive",
        )
        self.auth.keychain_store(token)
        return token

    def require_token(self) -> Token:
        token = self.auth.interactive_token()
        if not token:
            raise PermissionError(
                "no token — run `egzos init` (skeleton) / `egzos login` (Phase 2)"
            )
        return token
