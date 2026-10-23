# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The container as a resource server (spec/contracts/identity.md).

A request may carry an access token signed by the container's identity provider (Supabase Auth):
a person's, issued to this container's own OAuth client, or an agent's, issued to a client an admin
registered here. `Identity.verify` runs §3's seven checks in order, on every request, and answers
with the principal the token maps to, or `None`: every failure is the same answer, whichever check
failed. The JWT work is PyJWT's (buy, don't build). What is here is what egzos is: the order, the
binding to this one container, and the grants that decide what a verified caller may do (§4).

A verified caller reaches the engine as a `GrantToken`: a `Token` built per request from the grant
(and, for an agent, the registration intersected with it), never stored, so coverage, the gate and
the audience treat a granted person exactly as they treat a minted token.
"""

from __future__ import annotations

import ipaddress
import json
import threading
import time
import urllib.request
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import jwt

from egzos._types import AgentRegistration, IdentityState, UserGrant
from egzos.ledger import Ledger
from egzos.model import CAPABILITIES, ROLE_BUNDLES, Node, Token, now_iso

#: §2: never `none`, never a symmetric `HS*`. The asymmetric algorithms PyJWT verifies.
ASYMMETRIC_ALGORITHMS = frozenset(
    {"ES256", "ES384", "ES512", "RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "EdDSA"}
)
#: §3 check 4: `exp` and `iat` each get at most this much clock skew.
SKEW_SECONDS = 60
#: §3 check 1: an unknown `kid` re-fetches the key set at most once a minute.
JWKS_REFETCH_SECONDS = 60
#: A key set is a handful of public keys; anything larger is not one.
JWKS_MAX_BYTES = 64 * 1024
#: A bearer value longer than this is not a provider token, and is refused before any parsing.
TOKEN_MAX_CHARS = 16 * 1024

#: §2's keys this module reads, wire spelling.
IDENTITY_KEYS = (
    "identity.issuer",
    "identity.client_id",
    "identity.audience",
    "identity.algorithms",
    "identity.browser_origins",
)
#: The keys some code reads, so the only keys `config set` takes: §2's six (`confirm.allow_button`
#: is the confirm's, `egzos.confirm`).
SETTABLE_KEYS = (*IDENTITY_KEYS, "confirm.allow_button")

_NO_CLAIM_CHECKS = {
    # PyJWT verifies the signature; the claims are checked below, in §3's order, by this module.
    "verify_signature": True,
    "verify_exp": False,
    "verify_nbf": False,
    "verify_iat": False,
    "verify_aud": False,
    "verify_iss": False,
    "verify_sub": False,
    "verify_jti": False,
    "require": [],
}


class ConfigError(ValueError):
    """A config value this container will not hold. The message names the key, never a caller."""


class LastAdmin(Exception):
    """§4: the last live grant holding `admin` over `["*"]` is never revoked."""


# -- configuration (§2) --------------------------------------------------------------------------
def _loopback(host: str | None) -> bool:
    if host is None:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _origin(value: str, *, key: str) -> str:
    """An origin, exactly: `https://host[:port]`, or `http://` on a loopback host only."""
    parts = urlsplit(value)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise ConfigError(f"{key}: {value!r} is not an origin")
    if parts.scheme == "http" and not _loopback(parts.hostname):
        raise ConfigError(f"{key}: plain http is for a loopback host only")
    if parts.path or parts.query or parts.fragment or parts.username or parts.password:
        raise ConfigError(f"{key}: {value!r} is not an origin")
    return value


def validate(key: str, value: Any) -> Any:
    """The value `key` may hold, normalised, or `ConfigError`. None of these is a secret (§2)."""
    if key == "identity.issuer":
        if value is None:
            return None
        if not isinstance(value, str):
            raise ConfigError(f"{key}: a URL, or nothing")
        parts = urlsplit(value)
        if parts.scheme not in ("https", "http") or not parts.hostname:
            raise ConfigError(f"{key}: {value!r} is not a URL")
        if parts.scheme == "http" and not _loopback(parts.hostname):
            raise ConfigError(f"{key}: plain http is for a loopback host only")
        if parts.query or parts.fragment or parts.username or parts.password:
            raise ConfigError(f"{key}: an issuer has no query, fragment or credentials")
        return value
    if key == "identity.client_id":
        if value is None:
            return None
        if not isinstance(value, str) or not value or len(value) > 255 or value != value.strip():
            raise ConfigError(f"{key}: a client id, or nothing")
        if any(c.isspace() for c in value):
            raise ConfigError(f"{key}: a client id holds no whitespace")
        return value
    if key == "identity.audience":
        if not isinstance(value, str) or not value.strip() or len(value) > 255:
            raise ConfigError(f"{key}: an audience value")
        return value.strip()
    if key == "identity.algorithms":
        names = value.split() if isinstance(value, str) else []
        if not names:
            raise ConfigError(f"{key}: one or more of {' '.join(sorted(ASYMMETRIC_ALGORITHMS))}")
        refused = [n for n in names if n not in ASYMMETRIC_ALGORITHMS]
        if refused:
            raise ConfigError(f"{key}: {' '.join(refused)} refused; asymmetric algorithms only")
        return " ".join(dict.fromkeys(names))
    if key == "identity.browser_origins":
        if not isinstance(value, str):
            raise ConfigError(f"{key}: origins, separated by spaces")
        return " ".join(dict.fromkeys(_origin(o, key=key) for o in value.split()))
    if key == "confirm.allow_button":
        if isinstance(value, bool):
            return value
        if value in ("true", "false"):
            return value == "true"
        raise ConfigError(f"{key}: true or false")
    raise ConfigError(f"{key}: not a key this container sets")


@dataclass(frozen=True)
class Provider:
    """The provider this container trusts, read from config on every request (§2)."""

    issuer: str
    client_id: str
    audience: str
    algorithms: frozenset[str]

    @property
    def jwks_url(self) -> str:
        return self.issuer.rstrip("/") + "/.well-known/jwks.json"


# -- the key set (§3 check 1) --------------------------------------------------------------------
def _fetch_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 — the configured issuer
        body = response.read(JWKS_MAX_BYTES + 1)
    if len(body) > JWKS_MAX_BYTES:
        raise ValueError("key set too large")
    return json.loads(body)


def _keys(data: Any) -> dict[str, jwt.PyJWK]:
    """The asymmetric keys of a JWKS, by `kid`. A symmetric or unparseable key is skipped: it can
    never verify here, so it is as if the provider had not published it."""
    out: dict[str, jwt.PyJWK] = {}
    for jwk in (data.get("keys") if isinstance(data, dict) else None) or []:
        if not isinstance(jwk, dict) or not isinstance(jwk.get("kid"), str):
            continue
        if jwk.get("kty") == "oct":
            continue
        try:
            key = jwt.PyJWK(jwk)
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            continue
        out.setdefault(jwk["kid"], key)
    return out


class Jwks:
    """The provider's public keys, cached. An unknown `kid` re-fetches the set at most once a
    minute, so a stream of tokens naming made-up keys costs the provider one request a minute."""

    def __init__(
        self,
        url: str,
        *,
        fetch: Callable[[str], Any] = _fetch_json,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.url = url
        self._fetch = fetch
        self._clock = clock
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at: float | None = None
        self._lock = threading.Lock()

    def key(self, kid: str) -> jwt.PyJWK | None:
        with self._lock:
            key = self._keys.get(kid)
            if key is not None:
                return key
            now = self._clock()
            if self._fetched_at is not None and now - self._fetched_at < JWKS_REFETCH_SECONDS:
                return None
            self._fetched_at = now
            try:
                self._keys = _keys(self._fetch(self.url))
            except Exception:  # an unreachable or malformed provider fails closed, as one answer
                return None
            return self._keys.get(kid)


# -- the principal a verified token maps to (§4) --------------------------------------------------
@dataclass
class GrantToken(Token):
    """A `Token` built per request from a grant: never stored, never minted, never a bearer value.
    `sub` is the provider's user id; `client_id` is this container's own (a person) or a
    registered agent's. `acting_for` is the user an agent acts for (`details.for`, §3a)."""

    sub: str = ""
    client_id: str = ""
    acting_for: str | None = field(default=None, compare=False)
    #: The grant's or registration's display name: untrusted display data (rest.md §4.3).
    name: str = field(default="", compare=False)


def _number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _live(record: UserGrant | AgentRegistration | None) -> bool:
    return bool(record) and not record.get("revoked")


class Identity:
    """§3's verification and §4's grants, over the container's `IdentityState`."""

    def __init__(
        self,
        state: IdentityState,
        ledger: Ledger,
        config: Callable[[str], Any],
        *,
        ancestors: Callable[[str], list[str] | None],
        jwks: Callable[[str], Jwks] | None = None,
        atomic: Callable[[], AbstractContextManager[Any]] = nullcontext,
    ):
        self.state = state
        self.ledger = ledger
        self.config = config
        # One transaction on the container's store: a grant's check, its write and its entry land
        # together, and two concurrent revokes are serialised (BEGIN IMMEDIATE on sqlite).
        self.atomic = atomic
        # Node id -> the ids of its ancestors, itself included; None for a node that is absent.
        self.ancestors = ancestors
        self._jwks_for = jwks or self._jwks
        self._jwks_cache: dict[str, Jwks] = {}

    def _jwks(self, url: str) -> Jwks:
        cached = self._jwks_cache.get(url)
        if cached is None:
            cached = self._jwks_cache[url] = Jwks(url)
        return cached

    def provider(self) -> Provider | None:
        """The configured provider, or None: a container with none accepts only its own `Token`
        (§1), and is exactly the container that ran before v1.1."""
        issuer, client_id = self.config("identity.issuer"), self.config("identity.client_id")
        if not issuer or not client_id:
            return None
        return Provider(
            issuer=issuer,
            client_id=client_id,
            audience=self.config("identity.audience"),
            algorithms=frozenset(self.config("identity.algorithms").split())
            & ASYMMETRIC_ALGORITHMS,
        )

    # -- §3 ------------------------------------------------------------------------------------
    def verify(self, value: str, *, now: float | None = None) -> GrantToken | None:
        """The seven checks, in order. `None` is the one answer for every failure (§3)."""
        provider = self.provider()
        if provider is None or not isinstance(value, str) or not value:
            return None
        if len(value) > TOKEN_MAX_CHARS:
            return None
        # 1 · Signature: the key named by `kid`, its algorithm from the key, never the header alone.
        try:
            header = jwt.get_unverified_header(value)
        except jwt.PyJWTError:
            return None
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            return None
        key = self._jwks_for(provider.jwks_url).key(kid)
        if key is None:
            return None
        algorithm = key.algorithm_name
        if algorithm not in provider.algorithms:
            return None
        try:
            claims = jwt.decode(value, key.key, algorithms=[algorithm], options=_NO_CLAIM_CHECKS)
        except (jwt.PyJWTError, ValueError, TypeError):
            return None
        # 2 · Issuer, byte for byte.
        if claims.get("iss") != provider.issuer:
            return None
        # 3 · Audience: is, or contains.
        aud = claims.get("aud")
        if not (aud == provider.audience or (isinstance(aud, list) and provider.audience in aud)):
            return None
        # 4 · Time, with at most `SKEW_SECONDS` either way.
        at = time.time() if now is None else now
        exp, iat = claims.get("exp"), claims.get("iat")
        if not _number(exp) or not _number(iat):
            return None
        if exp + SKEW_SECONDS <= at or iat - SKEW_SECONDS > at:
            return None
        # 5 · Subject.
        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub:
            return None
        # 6 · Binding: this container's own client, or an agent registered here (§3a).
        client_id = claims.get("client_id")
        if not isinstance(client_id, str) or not client_id:
            return None
        person = client_id == provider.client_id
        if not person and not any(
            _live(r) for r in self.state.list_agent_registrations(client_id=client_id)
        ):
            return None
        # 7 · Grant: a live user grant, and for an agent a live registration serving this `sub`.
        if person:
            return self._person(sub, client_id)
        return self._agent(client_id, sub)

    # -- §4: what a verified caller may do ------------------------------------------------------
    def _person(self, sub: str, client_id: str) -> GrantToken | None:
        grant = self.state.get_user_grant(sub)
        if not _live(grant):
            return None
        return GrantToken(
            id=f"user:{sub}",
            principal="interactive",
            owner=f"user:{sub}",
            client=client_id,
            capabilities=sorted(grant["capabilities"]),
            scopes=list(grant["scopes"]),
            sub=sub,
            client_id=client_id,
            name=grant.get("name", ""),
        )

    def _agent(self, client_id: str, sub: str) -> GrantToken | None:
        grant = self.state.get_user_grant(sub)
        registration = self.state.get_agent_registration(client_id, sub)
        if not _live(grant) or not _live(registration):
            return None
        capabilities = sorted(set(registration["capabilities"]) & set(grant["capabilities"]))
        scopes = self.intersect(registration["scopes"], grant["scopes"])
        if not capabilities or not scopes:
            return None
        return GrantToken(
            id=f"agent:{client_id}:{sub}",
            principal="client",
            owner=f"agent:{client_id}",
            client=client_id,
            capabilities=capabilities,
            scopes=scopes,
            sub=sub,
            client_id=client_id,
            acting_for=f"user:{sub}",
            name=registration.get("name", ""),
        )

    def intersect(self, left: Iterable[str], right: Iterable[str]) -> list[str]:
        """Scopes covering exactly what both sides cover. Two scopes that both cover a node lie on
        its path, so one is the other's ancestor and the deeper one covers just their overlap; a
        pair on different branches covers nothing. Computed at check time, like coverage."""
        out: set[str] = set()
        right = list(right)
        for a in left:
            for b in right:
                if a == "*":
                    out.add(b)
                elif b == "*":
                    out.add(a)
                elif a in (self.ancestors(b) or ()):
                    out.add(b)
                elif b in (self.ancestors(a) or ()):
                    out.add(a)
        return sorted(out)

    def refresh(self, token: GrantToken) -> GrantToken | None:
        """The same caller as the grants stand now: a revoke since the request began counts."""
        if token.principal == "client":
            return self._agent(token.client_id, token.sub)
        return self._person(token.sub, token.client_id)

    def audience_tokens(self) -> list[GrantToken]:
        """Every live grant and registration, as the gate counts them (§4: audience is every
        live `Token`, user grant and agent registration whose coverage reaches a container)."""
        own = self.config("identity.client_id") or ""
        out: list[GrantToken] = []
        for grant in self.state.list_user_grants():
            person = self._person(grant["sub"], own) if _live(grant) else None
            if person:
                out.append(person)
        for registration in self.state.list_agent_registrations():
            if _live(registration):
                agent = self._agent(registration["client_id"], registration["sub"])
                if agent:
                    out.append(agent)
        return out

    # -- grants (§4) ----------------------------------------------------------------------------
    def grant_user(
        self,
        sub: str,
        *,
        name: str,
        role: str | None = None,
        capabilities: Iterable[str] | None = None,
        scopes: list[str],
        actor: str,
        principal: str,
    ) -> UserGrant:
        """Write (or replace) a person's grant and append `identity.grant`. Whoever calls this has
        already checked that the act is theirs: the owner `Token` at `link`, or an admin under
        the confirm at the door (§4)."""
        if principal != "interactive":
            raise PermissionError("granting access is a person's act")
        if not isinstance(sub, str) or not sub.strip() or len(sub) > 255:
            raise ValueError("a grant names the provider's user id")
        if (role is None) == (capabilities is None):
            raise ValueError("a grant names a role or capabilities, not both")
        if role is not None and role not in ROLE_BUNDLES:
            raise ValueError("unknown role")
        caps = sorted(ROLE_BUNDLES[role]) if role is not None else sorted(set(capabilities or ()))
        if not caps or any(c not in CAPABILITIES for c in caps):
            raise ValueError("unknown capability")
        if not scopes:
            raise ValueError("a grant covers at least one scope")
        grant: UserGrant = {
            "sub": sub,
            "name": name,
            "capabilities": caps,
            "scopes": list(scopes),
            "created_at": now_iso(),
            "revoked": False,
        }
        with self.atomic():
            # Re-granting the last whole-container admin something narrower removes the last
            # admin as surely as revoking it does (§4), so it is refused the same way.
            narrows = not _whole(grant) and self._last_admin(sub)
            if not narrows:
                self.state.put_user_grant(grant)
                self.ledger.append(
                    "identity.grant",
                    actor=actor,
                    principal=principal,
                    subject=sub,
                    kind="user",
                    outcome="granted",
                    capabilities=caps,
                    scopes=list(scopes),
                )
                return grant
        self._refused("identity.grant", sub, actor=actor, principal=principal)
        raise LastAdmin(sub)

    def revoke_user(self, sub: str, *, actor: str, principal: str) -> bool:
        """Revoke a person's grant. Narrowing is never gated (§4). `False` for no live grant; the
        last live grant holding `admin` over `["*"]` raises `LastAdmin` and appends a refusal.

        The read, the last-admin check, the write and the entry are one transaction, so two
        concurrent revokes of the last two whole-container admins cannot both pass the check, and
        a revoke never stands without its entry. The refusal is appended after it, not inside: a
        refusal rolled back with the act it refused would leave no trace."""
        with self.atomic():
            grant = self.state.get_user_grant(sub)
            if not _live(grant):
                return False
            if not self._last_admin(sub):
                self.state.put_user_grant({**grant, "revoked": True})
                self.ledger.append(
                    "identity.revoke",
                    actor=actor,
                    principal=principal,
                    subject=sub,
                    kind="user",
                    outcome="revoked",
                    capabilities=grant["capabilities"],
                    scopes=grant["scopes"],
                )
                return True
        self._refused("identity.revoke", sub, actor=actor, principal=principal)
        raise LastAdmin(sub)

    def _refused(self, event: str, sub: str, *, actor: str, principal: str) -> None:
        self.ledger.append(
            event,
            actor=actor,
            principal=principal,
            subject=sub,
            kind="user",
            outcome="refused",
            reason="last_admin",
        )

    def _last_admin(self, sub: str) -> bool:
        """Whether `sub` holds the only live grant with `admin` over the whole container."""
        grants = self.state.list_user_grants()
        mine = next((g for g in grants if g["sub"] == sub), None)
        return bool(mine and _whole(mine)) and not any(
            _whole(g) for g in grants if g["sub"] != sub
        )


def _whole(grant: UserGrant) -> bool:
    return _live(grant) and "admin" in grant["capabilities"] and "*" in grant["scopes"]


def node_ancestors(get_node: Callable[[str], Node | None], ancestors: Callable[[Node], list[Node]]):
    """`Identity`'s `ancestors` from the node service's own two reads."""

    def lookup(node_id: str) -> list[str] | None:
        node = get_node(node_id)
        return [n.id for n in ancestors(node)] if node else None

    return lookup
