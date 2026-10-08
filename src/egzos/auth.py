# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
Principals and tokens, skeleton edition (v0.4 §5, v0.3 §5). Bearer tokens cannot prove a human;
tokens carry `principal: interactive | client`. Human-only acts demand the interactive principal
AND the step-up tap (`egzos.authz.presence`): the token says who may act, the tap that a person
is present and decided.

The OS keychain is stood in for by a mode-0600 file under the container home. Machine clients
never touch it; they receive their own client tokens.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from pathlib import Path

from egzos._ids import ulid
from egzos.backends.base import Backend
from egzos.ledger import Ledger
from egzos.model import ROLE_BUNDLES, TOKEN_PRINCIPALS, Token, now_iso


class AuthError(Exception):
    pass


PREFIX = "egz_"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_secret(token_id: str) -> str:
    """The bearer value: `egz_<id>_<256 random bits>`. The id half finds the record; only the
    sha256 of the whole value is stored, so the database and the audit chain never hold it."""
    return f"{PREFIX}{token_id}_{secrets.token_urlsafe(32)}"


def token_id_of(value: str) -> str | None:
    """The public id inside a bearer value, or None when the value is not one."""
    if not value.startswith(PREFIX):
        return None
    rest = value[len(PREFIX):]
    tid, sep, _ = rest.partition("_")
    return tid if sep and len(tid) == 26 else None


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
        if by_principal != "interactive":
            # Minting is the owner's act: a client principal never widens itself (or anyone).
            raise AuthError("minting a token is the owner's act")
        if role not in ROLE_BUNDLES:
            raise AuthError(f"unknown role {role!r}")
        if principal not in TOKEN_PRINCIPALS:
            # `none` is an audit-only principal (events.md §2): no token is ever minted for it.
            raise AuthError(f"unknown token principal {principal!r}")
        token = Token(
            id=ulid(),
            principal=principal,
            owner=owner,
            client=client,
            capabilities=sorted(ROLE_BUNDLES[role]),
            scopes=scopes,
        )
        secret = new_secret(token.id)
        token.secret_hash = _hash(secret)
        self.backend.put_token(token)
        token.secret = secret
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
        if not token.secret:
            raise AuthError("only a freshly minted token can be stored; its value is not kept")
        fd = os.open(self.keychain, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps({"token": token.secret, "stored_at": now_iso()}))
        os.chmod(self.keychain, 0o600)

    def interactive_token(self) -> Token | None:
        """The owner's interactive token from the keychain — `login` is what puts it there."""
        env = os.environ.get("EGZOS_TOKEN")
        if env:
            return self.use(env)
        if not self.keychain.exists():
            return None
        return self.use(json.loads(self.keychain.read_text())["token"])

    def use(self, value: str) -> Token | None:
        """The token a bearer value proves, or None. Every failure looks the same to the caller."""
        tid = token_id_of(value or "")
        token = self.backend.get_token(tid) if tid else None
        if not token or not token.live or not token.secret_hash:
            return None
        if not secrets.compare_digest(_hash(value), token.secret_hash):
            return None
        token.last_used = now_iso()
        self.backend.put_token(token)
        return token
