# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
Principals and tokens, skeleton edition (v0.4 §5, v0.3 §5). Bearer tokens cannot prove a human;
tokens carry `principal: interactive | client`. Human-only acts demand the interactive principal
(the step-up tap arrives in Phase 2.2 — here the interactive owner token IS the proof).

The OS keychain is stood in for by a mode-0600 file under the container home. Machine clients
never touch it; they receive their own client tokens.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from egzos._ids import ulid
from egzos.backends.base import Backend
from egzos.ledger import Ledger
from egzos.model import ROLE_BUNDLES, Token, now_iso


class AuthError(Exception):
    pass


class Auth:
    def __init__(self, home: Path, backend: Backend, ledger: Ledger):
        self.home = Path(home)
        self.backend = backend
        self.ledger = ledger
        self.keychain = self.home / "keychain.json"

    def mint(
        self,
        *,
        principal: str,
        owner: str,
        client: str,
        role: str,
        scopes: list[str],
        actor: str,
        by_principal: str,
    ) -> Token:
        if role not in ROLE_BUNDLES:
            raise AuthError(f"unknown role {role!r}")
        token = Token(
            id=ulid(),
            principal=principal,
            owner=owner,
            client=client,
            capabilities=sorted(ROLE_BUNDLES[role]),
            scopes=scopes,
        )
        self.backend.put_token(token)
        self.ledger.append(
            "token.mint",
            actor=actor,
            principal=by_principal,
            subject=token.id,
            token_principal=principal,
            client=client,
            role=role,
            scopes=scopes,
        )
        return token

    def revoke(self, token_id: str, *, actor: str, principal: str) -> bool:
        token = self.backend.get_token(token_id)
        if not token:
            return False
        token.revoked = True
        self.backend.put_token(token)
        self.ledger.append("token.revoke", actor=actor, principal=principal, subject=token.id)
        return True

    # -- keychain stand-in -------------------------------------------------------------
    def keychain_store(self, token: Token) -> None:
        self.keychain.write_text(json.dumps({"token": token.id, "stored_at": now_iso()}))
        os.chmod(self.keychain, 0o600)

    def interactive_token(self) -> Token | None:
        """The owner's interactive token from the keychain — `login` is what puts it there."""
        env = os.environ.get("EGZOS_TOKEN")
        if env:
            return self.use(env)
        if not self.keychain.exists():
            return None
        return self.use(json.loads(self.keychain.read_text())["token"])

    def use(self, token_id: str) -> Token | None:
        token = self.backend.get_token(token_id)
        if not token or token.revoked:
            return None
        token.last_used = now_iso()
        self.backend.put_token(token)
        return token
