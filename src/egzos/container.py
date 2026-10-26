# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The container — the user's home (v0.4 §1). One process-local assembly of backend, ledger, nodes,
store, blobs and auth rooted at EGZOS_HOME (default ~/.egzos). The container is the availability
boundary (v0.4 §16): nothing else can serve what it can't.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from egzos._types import CONTAINER_CONFIG_DEFAULTS, CONTAINER_CONFIG_FIELD_FROM_WIRE_KEY
from egzos.auth import Auth, home_secret
from egzos.binding import HomeBinding, HomeBindingError
from egzos.confirm import Confirm
from egzos.identity import (
    SETTABLE_KEYS,
    ConfigError,
    GrantToken,
    Identity,
    node_ancestors,
    validate,
)
from egzos.ledger import Ledger
from egzos.model import Token
from egzos.resolver import Resolver
from egzos.store import BlobStore, NodeService, Store
from egzos.store.blobs import _is_digest
from egzos.store.find import shown
from egzos.store.uploads import Uploads
from egzos.trust import GRANT_KEY_BYTES, GRANT_KEY_FILE, TrustEngine

OWNER = "self"

__all__ = ["OWNER", "Container", "HomeBindingError", "default_home"]


def _step_up_window() -> int:
    from egzos.authz.presence import window_seconds

    return window_seconds()


def default_home() -> Path:
    return Path(os.environ.get("EGZOS_HOME", Path.home() / ".egzos"))


class Container:
    def __init__(self, home: Path | None = None):
        self.home = Path(home or default_home())
        # The database holds the chain, every item and the token hashes: the owner's only. Created
        # 0700 (no window at the umask's mode), then pinned 0700 if it already existed.
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.home, 0o700)
        # storage.md §3.7: the database EGZOS_DATABASE_URL names, else the home's own egzos.db.
        # The home's binding is checked here, before anything is built that could serve.
        self.binding = HomeBinding(self.home)
        self.backend = self.binding.open()
        self._closed = False
        self.ledger = Ledger(self.backend)
        self.nodes = NodeService(self.backend, self.ledger)
        self.blobs = BlobStore(self.home / "blobs")
        self.store = Store(self.backend, self.ledger, self.nodes, self.blobs)
        self.auth = Auth(self.home, self.backend, self.ledger)
        self.trust = TrustEngine(self.backend, self.ledger, self.nodes)
        self.resolver = Resolver(self.backend, self.ledger, self.nodes, self.trust)
        self.store.covers = self.trust.covers
        self.store.shown = lambda token, item, node: shown(self, token, item, node)
        self.nodes.covers = self.trust.covers
        self.identity = Identity(
            self.backend,
            self.ledger,
            self.config_value,
            ancestors=node_ancestors(self.backend.get_node, self.nodes.ancestors),
            atomic=self.backend.atomic,
        )
        self.trust.principals = self.identity.audience_tokens
        self.trust.refresh = self._refresh
        self.trust.promote_blob = lambda sha: _is_digest(sha) and self.blobs.promote(sha)
        # rest.md §6: the grant key, made at first need in the home, never a config key or a row;
        # whom a grant names, as they stand now, an id no record holds any more as a revoked
        # stand-in, so a refusal is still attributed to it; and what is shown.
        self.trust.grant_key = lambda: home_secret(self.home / GRANT_KEY_FILE, GRANT_KEY_BYTES)
        self.trust.named = lambda tid: (
            self.identity.named(tid) or self.backend.get_token(tid)
            or Token(id=tid, principal="client", owner=tid, client="", capabilities=[],
                     scopes=[], revoked=True))
        self.trust.shown = self.store.shown
        self.uploads = Uploads(self.backend, self.ledger, self.blobs, self.store)
        self.confirm = Confirm(
            self.backend, self.ledger, self.config_value, window_seconds=_step_up_window,
            salt=self._salt,
        )

    def _salt(self) -> str:
        """Per container and fixed for its life: the personal root's id. With no root there is
        no salt, and no handle is handed out (a1r on #290)."""
        root = self.nodes.user_root()
        if root is None:
            raise RuntimeError("this container is not initialised")
        return root.id

    def _refresh(self, token: Token) -> Token | None:
        """The caller as it stands now: a minted token re-read, a grant re-derived (§4)."""
        if isinstance(token, GrantToken):
            return self.identity.refresh(token)
        return self.backend.get_token(token.id)

    # -- the container-config object (container.md §8) ------------------------------------------
    def config_value(self, key: str) -> Any:
        """The value of a wire key as set, or its default. Absence is tested by absence, never by
        truthiness (`CONTAINER_CONFIG_FIELD_FROM_WIRE_KEY`): an empty string set is a value."""
        stored = self.backend.get_config()
        if key in stored:
            return stored[key]
        return CONTAINER_CONFIG_DEFAULTS[CONTAINER_CONFIG_FIELD_FROM_WIRE_KEY[key]]  # type: ignore[literal-required]

    def set_config(self, key: str, value: Any, *, token: Token) -> Any:
        """Set a key: an `admin` act over the whole container, from a person (§8), recorded by
        `config.set` with the value as it then stands. Only the keys code here reads are settable;
        the rest are still the constants they always were, and setting one would be a lie."""
        if token.principal != "interactive" or not token.has("admin") or "*" not in token.scopes:
            raise PermissionError("changing the container's config is an admin's act")
        if key not in SETTABLE_KEYS:
            raise ConfigError(f"{key}: not a key this container sets")
        value = validate(key, value)
        with self.backend.atomic():
            self.backend.put_config(key, value)
            self.ledger.append(
                "config.set", actor=token.owner, principal=token.principal, key=key, value=value
            )
        return value

    @property
    def initialized(self) -> bool:
        return self.backend.find_root("user") is not None

    def init(self) -> Token:
        """Create the roots and the owner's interactive token; put it in the keychain stand-in.
        `login` (device-code) replaces this step from Phase 2; the skeleton is single-user.

        The check and the creation are one transaction (#136): BEGIN IMMEDIATE takes the write
        lock first, so a second `init` racing this one waits, then finds the container
        initialized, and never mints a second owner or a second set of roots.

        On a named database this block is the home's make (storage.md §3.7): it finds the chain
        empty and appends its first entry, or stops, and the binding is written once it commits."""
        with self.backend.atomic():
            making = self.binding.making(self.backend)
            token = self._init_locked()
        if making:
            self.binding.made(self.backend)
        return token

    def close(self) -> None:
        """A clean close: a bound home records the newest entry it has seen (storage.md §3.7),
        and the connection is let go. A second call does nothing."""
        if self._closed:
            return
        self._closed = True
        self.binding.record(self.backend)
        self.backend.db.close()

    def _init_locked(self) -> Token:
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
        # Inside the lock, so a racing init that waits on it finds the keychain already written.
        self.auth.keychain_store(token)
        return token

    def require_token(self) -> Token:
        token = self.auth.interactive_token()
        if not token:
            raise PermissionError(
                "no token — run `egzos init` (skeleton) / `egzos login` (Phase 2)"
            )
        return token
