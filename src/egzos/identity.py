# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The container as a resource server (spec/contracts/identity.md).

A request may carry an access token signed by the container's identity provider (Supabase Auth):
a person's, issued to this container's own OAuth client, or an agent's, issued to a client that the
person it serves registered here (§4: each person registers their own, v0.7 §AB).
`Identity.verify` runs §3's seven checks in order, on every request, and answers
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
import re
import threading
import time
import unicodedata
import urllib.request
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlsplit

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
#: The keys some code reads, so the only keys `config set` takes: §2's seven (`identity.origin` is
#: the door's, `egzos.api`; `confirm.allow_button` the confirm's, `egzos.confirm`), and the two the
#: upload reads (`rest.md` §4.4).
SETTABLE_KEYS = (
    *IDENTITY_KEYS, "identity.origin", "confirm.allow_button", "blobs.upload_max_bytes",
    "blobs.staging_retention_days",
)
#: The bounds of the two numeric keys: an upload of 1 byte to 1 TiB; 0 days to a century.
_NUMBERS = {"blobs.upload_max_bytes": (1, 1 << 40), "blobs.staging_retention_days": (0, 36500)}

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


#: rest.md §4.3: the live registrations one person holds at most, so the audience the gate
#: computes over registrations (§4) stays bounded.
MAX_AGENTS = 16


class TooManyAgents(Exception):
    """rest.md §4.3: the person already holds `MAX_AGENTS` live registrations. Their own fact."""


#: A name shown to a person deciding something — who would newly see an item, an agent's own
#: claim, a device — is at most this long.
DISPLAY_NAME_MAX = 128
#: Characters a display name never holds: controls, and the formatting characters (bidi
#: overrides among them) that make text read other than it is (a6 on #289).
_HIDDEN = frozenset({"Cc", "Cf", "Zl", "Zp"})


def display_name(value: Any, *, limit: int = DISPLAY_NAME_MAX) -> str:
    """A display name as given, or `ValueError`. Untrusted display data every surface escapes;
    this keeps it short and free of characters that hide what it says."""
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"a name of 1 to {limit} characters")
    if any(unicodedata.category(ch) in _HIDDEN for ch in value):
        raise ValueError("a name holds no control or formatting characters")
    return value


def provider_id(value: Any, what: str = "an id the provider issued") -> str:
    """An id the provider issued — a user's, an OAuth client's, an authorization's — as given, or
    `ValueError(what)`: 1 to 255 characters, with no whitespace and, as in a display name, no
    control or formatting character, so it reads as what it is wherever it is listed."""
    if not isinstance(value, str) or not value or len(value) > 255 or any(
        ch.isspace() or unicodedata.category(ch) in _HIDDEN for ch in value
    ):
        raise ValueError(what)
    return value


def principal_id(client_id: str | None, sub: str) -> str:
    """A provider principal's `Token.id`, naming exactly one `(client_id, sub)` pair
    (GHSA-9g46-638p-v4xm): `user:<sub>` for a person, `agent:<client_id>:<sub>` for an agent, as
    ever, where no part holds `%` or `:`, a UUID among them. Otherwise the kind is `user%` or
    `agent%`, which no id written before held, and each part has `%` written `%25` and `:` `%3A`.
    The owner and `acting_for` are attribution, not ids: one part each, raw (identity.md §3a)."""
    kind, parts = ("user", [sub]) if client_id is None else ("agent", [client_id, sub])
    if any("%" in p or ":" in p for p in parts):
        kind, parts = kind + "%", [p.replace("%", "%25").replace(":", "%3A") for p in parts]
    return ":".join([kind, *parts])


def principal_parts(token_id: str) -> tuple[str | None, str] | None:
    """The `(client_id, sub)` pair a provider principal's id names, `client_id` None for a person:
    `principal_id` read back. None for any string `principal_id` would not write, a container
    `Token`'s ULID among them, so no other spelling names a pair."""
    parts = [unquote(p) for p in token_id.split(":")[1:]]
    if not 1 <= len(parts) <= 2 or not all(parts):
        return None
    pair = (None, parts[0]) if len(parts) == 1 else (parts[0], parts[1])
    # The kind is never parsed: this round trip is what refuses a foreign or mismatched one.
    return pair if principal_id(*pair) == token_id else None


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


_LABEL = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
#: An origin as a browser sends one (RFC 6454 §6.2): a scheme, a lowercase ASCII host or a
#: bracketed IPv6 address, and a port, with nothing around them.
_ORIGIN = re.compile(rf"(https?)://({_LABEL}(?:\.{_LABEL})*|\[[0-9a-f:]+\])(?::([1-9][0-9]*))?")
_DEFAULT_PORT = {"https": 443, "http": 80}


def _origin(value: str, *, key: str) -> str:
    """An origin, exactly as a browser sends it: `https://host[:port]`, or `http://` on a loopback
    host only, with no default port and nothing else. Only such a value can match an `Origin`
    header, and only such a value is published (§7) as it is held."""
    match = _ORIGIN.fullmatch(value)
    scheme, host, port = match.groups() if match else ("", "", None)
    if host.startswith("["):  # an IPv6 address, written as a browser writes it, or nothing
        try:
            host = host[1:-1] if ipaddress.IPv6Address(host[1:-1]).compressed == host[1:-1] else ""
        except ValueError:
            host = ""
    if not host or port is not None and (
            len(port) > 5 or int(port) > 65535 or int(port) == _DEFAULT_PORT[scheme]):
        raise ConfigError(f"{key}: {value!r} is not an origin")
    if scheme == "http" and not _loopback(host):
        raise ConfigError(f"{key}: plain http is for a loopback host only")
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
    if key == "identity.origin":
        if value is None:
            return None
        if not isinstance(value, str):
            raise ConfigError(f"{key}: an origin, or nothing")
        return _origin(value, key=key)  # one origin, held as a browser origin is
    if key == "confirm.allow_button":
        if isinstance(value, bool):
            return value
        if value in ("true", "false"):
            return value == "true"
        raise ConfigError(f"{key}: true or false")
    if key in _NUMBERS:
        low, high = _NUMBERS[key]
        if isinstance(value, str) and value.isdigit() and value.isascii():
            value = int(value)
        if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
            raise ConfigError(f"{key}: a whole number from {low} to {high}")
        return value
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
    #: When the person last signed in at the provider (the newest `amr` timestamp), for the acts
    #: that need a fresh sign-in (rest.md §4.3). None when the token says nothing.
    auth_time: int | None = field(default=None, compare=False)


def _number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _auth_time(amr: Any) -> int | None:
    """The newest authentication time in Supabase's `amr` claim: `[{method, timestamp}, …]`."""
    times = [
        int(entry["timestamp"]) for entry in amr or ()
        if isinstance(entry, dict) and _number(entry.get("timestamp"))
    ] if isinstance(amr, list) else []
    return max(times) if times else None


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
        who = self._person(sub, client_id) if person else self._agent(client_id, sub)
        if who is not None:
            who.auth_time = _auth_time(claims.get("amr"))
        return who

    # -- §4: what a verified caller may do ------------------------------------------------------
    def _person(self, sub: str, client_id: str) -> GrantToken | None:
        grant = self.state.get_user_grant(sub)
        if not _live(grant):
            return None
        return GrantToken(
            id=principal_id(None, sub),
            principal="interactive",
            owner=f"user:{sub}",
            client=client_id,
            capabilities=sorted(grant["capabilities"]),
            scopes=list(grant["scopes"]),
            created_at=grant["created_at"],  # rest.md §6 check 5: a grant written since is new
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
            id=principal_id(client_id, sub),
            principal="client",
            owner=f"agent:{client_id}",
            client=client_id,
            capabilities=capabilities,
            scopes=scopes,
            created_at=max(grant["created_at"], registration["created_at"]),
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

    def named(self, token_id: str) -> GrantToken | None:
        """The person or agent a `GrantToken` id names, as the grants stand now (rest.md §6 check
        5): the one pair `principal_parts` reads from it. Revoked since, a stand-in that is revoked
        and holds nothing, so a refusal is still attributed to whom the grant named. None for an
        id that is not a grant's."""
        pair = principal_parts(token_id)
        if pair is None:
            return None
        client_id, sub = pair
        if client_id is None:
            own = self.config("identity.client_id") or ""
            return self._person(sub, own) or GrantToken(
                id=token_id, principal="interactive", owner=f"user:{sub}", client=own,
                capabilities=[], scopes=[], revoked=True, sub=sub, client_id=own)
        if self.state.get_agent_registration(client_id, sub) is None:
            return None
        return self._agent(client_id, sub) or GrantToken(
            id=token_id, principal="client", owner=f"agent:{client_id}", client=client_id,
            capabilities=[], scopes=[], revoked=True, sub=sub, client_id=client_id,
            acting_for=f"user:{sub}")

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
    @staticmethod
    def expand(role: Any, capabilities: Any) -> list[str]:
        """A grant's capabilities, sorted: a role's bundle expanded at grant time, as at mint
        (capabilities.md §2), or the capabilities named. It takes a request body's values as they
        came, so anything else is a `ValueError`: both or neither, an unknown role, or other than
        a non-empty list of known capabilities."""
        if (role is None) == (capabilities is None):
            raise ValueError("a grant names a role or capabilities, not both")
        if role is not None:
            if not isinstance(role, str) or role not in ROLE_BUNDLES:
                raise ValueError("unknown role")
            return sorted(ROLE_BUNDLES[role])
        if not isinstance(capabilities, list) or not capabilities or any(
            c not in CAPABILITIES for c in capabilities
        ):
            raise ValueError("unknown capability")
        return sorted(set(capabilities))

    @staticmethod
    def user_id(value: Any) -> str:
        """The provider's user id a grant names, read as `provider_id` reads any id the provider
        issued. A provider's user id is a UUID."""
        return provider_id(value, "a grant names the provider's user id")

    def grant_user(
        self,
        sub: str,
        *,
        name: str,
        role: str | None = None,
        capabilities: list[str] | None = None,
        scopes: list[str],
        actor: str,
        principal: str,
    ) -> UserGrant:
        """Write (or replace) a person's grant and append `identity.grant`. Whoever calls this has
        already checked that the act is theirs: the owner `Token` at `link`, or an admin under
        the confirm at the door (§4). `capabilities` is the names, which `expand` checks: a list,
        never a lone string."""
        if principal != "interactive":
            raise PermissionError("granting access is a person's act")
        sub = self.user_id(sub)
        name = display_name(name)
        caps = self.expand(role, capabilities)
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
            if not self._narrows(sub, caps, grant["scopes"]):
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
        """Revoke a person's grant and every live registration serving them, each with its own
        `identity.revoke`, so a later grant to that `sub` starts with no agents (§4). The caller
        has judged the act: an admin narrowing their own access (never gated), an admin ending
        someone else's under the confirm at the REST door, or the owner `Token` on the CLI or the
        lifeboat, the recovery factor (§AD: no confirm, audited). `False` for no live grant; the
        last live grant holding `admin` over `["*"]` raises `LastAdmin` and appends a refusal.

        The read, the last-admin check, the writes and the entries are one transaction, so two
        concurrent revokes of the last two whole-container admins cannot both pass the check, and
        a revoke never stands without its entries. The refusal is appended after it, not inside: a
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
                for agent in self.serving(sub):
                    self.revoke_agent(agent["client_id"], sub, actor=actor, principal=principal)
                return True
        self._refused("identity.revoke", sub, actor=actor, principal=principal)
        raise LastAdmin(sub)

    def revoke_agent(self, client_id: str, sub: str, *, actor: str, principal: str) -> bool:
        """Revoke the live registration of `client_id` serving `sub` and append its
        `identity.revoke` (`kind: agent`, `for` the person it served), as one transaction: of two
        concurrent revokes of one registration, one ends it and the other finds nothing. The caller
        has judged the act: the person it serves (never gated), an admin ending someone else's under
        the confirm at the REST door, or a revoke of the grant it serves (§4). `False` for none."""
        with self.atomic():
            registration = self.state.get_agent_registration(client_id, sub)
            if not _live(registration):
                return False
            self.state.put_agent_registration({**registration, "revoked": True})
            self.ledger.append(
                "identity.revoke", actor=actor, principal=principal, subject=client_id,
                kind="agent", outcome="revoked", capabilities=registration["capabilities"],
                scopes=registration["scopes"], **{"for": f"user:{sub}"},
            )
        return True

    def serving(self, sub: str) -> list[AgentRegistration]:
        """Every live registration serving `sub`. storage.md §3.2 lists registrations by
        `client_id` only, so this scans them all: a filter by `sub` would be a contract change."""
        return [r for r in self.state.list_agent_registrations() if r["sub"] == sub and _live(r)]

    def exceeds(self, caller: Token, capabilities: list[str], scopes: list[str]) -> bool:
        """Whether a grant of these goes beyond `caller`'s own (rest.md §4.3): a capability the
        caller lacks, or a scope their coverage does not reach. `*` is the whole container, which
        only a caller holding `*` reaches."""
        return not set(capabilities) <= set(caller.capabilities) or self._wider(
            caller.scopes, scopes
        )

    def opens(
        self, sub: str, name: str, capabilities: list[str], scopes: list[str]
    ) -> list[tuple[str, str]]:
        """Whom granting `sub` these would newly let see something, as sorted `(member, display
        name)` pairs: rest.md §4.2's audience delta for a grant. The person, unless their live
        grant already reaches all of it (a revoked one reaches nothing), and each agent serving
        them whose reach, its registration intersected with the grant (§4), the grant widens."""
        old = self.state.get_user_grant(sub)
        had_caps, had_scopes = (old["capabilities"], old["scopes"]) if _live(old) else ([], [])
        out = [(principal_id(None, sub), name)] if self._wider(had_scopes, scopes) else []
        for agent in self.serving(sub):
            before = self._reach(agent, had_caps, had_scopes)
            if self._wider(before, self._reach(agent, capabilities, scopes)):
                out.append((principal_id(agent["client_id"], sub), agent["name"]))
        return sorted(out)

    def _reach(
        self, agent: AgentRegistration, capabilities: list[str], scopes: list[str]
    ) -> list[str]:
        """What an agent covers under a grant of these, as at check time (`_agent`): nothing
        without a capability in common, else its scopes intersected with the grant's."""
        if not set(agent["capabilities"]) & set(capabilities):
            return []
        return self.intersect(agent["scopes"], scopes)

    def _wider(self, before: list[str], after: list[str]) -> bool:
        """Whether `after` reaches a node `before` does not. Coverage runs down the path, only
        `*` reaches the whole container, and an absent node counts as one `before` misses."""
        if "*" in before:
            return False
        return "*" in after or any(not set(before) & set(self.ancestors(s) or ()) for s in after)

    def refuse_narrowing(
        self, sub: str, capabilities: list[str], scopes: list[str], *, actor: str, principal: str
    ) -> bool:
        """rest.md §4.3's check before any leg of the confirm: where granting `sub` these would
        narrow the last live grant holding `admin` over `["*"]`, append `identity.grant`'s
        refusal and answer True. `grant_user` checks again under its lock."""
        if not self._narrows(sub, capabilities, scopes):
            return False
        self._refused("identity.grant", sub, actor=actor, principal=principal)
        return True

    def _narrows(self, sub: str, capabilities: list[str], scopes: list[str]) -> bool:
        """Whether granting `sub` anything short of `admin` over `["*"]` takes it from the last
        grant holding it: that removes the last admin as surely as revoking it does (§4)."""
        return not ("admin" in capabilities and "*" in scopes) and self._last_admin(sub)

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

    # -- agent registrations (§4, rest.md §4.3) -------------------------------------------------
    def register_agent(self, person: GrantToken, client_id: str, *, authorization_id: str,
                       name: str, capabilities: list[str], scopes: list[str],
                       after: int | None = None) -> AgentRegistration | None:
        """Write a registration serving `person` and append `identity.grant` attributed to them:
        `kind: agent`, `for` the person, and `authorization_id` as the caller claimed it, never a
        verified fact. Each person registers their own (v0.7 §AB). The caller has judged the act,
        the confirm included, in the transaction this joins, and may have read the chain through
        seq `after`. The rest of it and the cap are checked with the write, under one lock: of two
        registrations naming one authorization at most one lands (None for the other and every
        later one), and two at 15 never both take the 16th (`TooManyAgents`)."""
        if not isinstance(person, GrantToken) or person.principal != "interactive":
            raise PermissionError("registering an agent is a person's act")
        registration: AgentRegistration = {
            "client_id": client_id, "sub": person.sub, "name": name,
            "capabilities": list(capabilities), "scopes": list(scopes), "created_at": now_iso(),
            "revoked": False,
        }
        with self.atomic():
            if self.claimed(authorization_id, after):
                return None
            if self.full(person.sub, client_id):
                raise TooManyAgents(person.sub)
            self.state.put_agent_registration(registration)
            self.ledger.append(
                "identity.grant", actor=person.owner, principal=person.principal,
                subject=client_id, kind="agent", outcome="granted",
                capabilities=registration["capabilities"], scopes=registration["scopes"],
                authorization_id=authorization_id, **{"for": f"user:{person.sub}"},
            )
        return registration

    def full(self, sub: str, client_id: str) -> bool:
        """Whether `sub` holds `MAX_AGENTS` live registrations besides one of `client_id`, which
        registering it again replaces: a 17th is refused, never written (rest.md §4.3)."""
        return sum(r["client_id"] != client_id for r in self.serving(sub)) >= MAX_AGENTS

    def claimed(self, authorization_id: str, after: int | None = None) -> bool:
        """Whether a registration was ever written for this authorization, which keys one
        (rest.md §4.3). Its only record is `identity.grant`'s `details.authorization_id`: neither
        identity.md §4's record nor storage.md §3.2 holds it, so this reads the chain; with
        `after`, only its tail past that seq, so a lock never waits on a read of all of it."""
        return any(
            e["event"] == "identity.grant" and e["details"].get("kind") == "agent"
            and e["details"].get("authorization_id") == authorization_id
            for e in (self.ledger.backend.audit_iter() if after is None
                      else self.ledger.tail(self.ledger.tail(1)[-1]["seq"] - after))
        )

    def acted(self, client_id: str, sub: str) -> list[dict[str, Any]]:
        """What an agent did for one person, oldest first: every entry attributed to it that
        names that person (`details.for`, §3a), its refusals included. Read from the chain in one
        pass, as `last_seen` reads it (rest.md §4.3's log)."""
        pair = (f"agent:{client_id}", f"user:{sub}")
        return [e for e in self.ledger.backend.audit_iter()
                if (e["actor"], e["details"].get("for")) == pair]

    def last_seen(self, registrations: Iterable[AgentRegistration]) -> dict[tuple[str, str], str]:
        """When each agent last acted for the person it serves, by `(client_id, sub)`: its newest
        entry attributed to it and naming that person (`details.for`, §3a). A pair never seen is
        absent. Read from the chain in one pass, as nothing else records it (rest.md §4.3)."""
        wanted = {(f"agent:{r['client_id']}", f"user:{r['sub']}"): (r["client_id"], r["sub"])
                  for r in registrations}
        seen: dict[tuple[str, str], str] = {}
        if wanted:
            for entry in self.ledger.backend.audit_iter():
                pair = wanted.get((entry["actor"], entry["details"].get("for")))
                if pair is not None:
                    seen[pair] = entry["ts"]
        return seen


def _whole(grant: UserGrant) -> bool:
    return _live(grant) and "admin" in grant["capabilities"] and "*" in grant["scopes"]


def node_ancestors(get_node: Callable[[str], Node | None], ancestors: Callable[[Node], list[Node]]):
    """`Identity`'s `ancestors` from the node service's own two reads."""

    def lookup(node_id: str) -> list[str] | None:
        node = get_node(node_id)
        return [n.id for n in ancestors(node)] if node else None

    return lookup
