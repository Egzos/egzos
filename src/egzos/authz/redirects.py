# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The redirect-URI allowlist (authorization-server.md §5.1, §5.2).

Matching is exact string comparison: no prefix, no wildcard, no query or fragment tolerance, no
scheme, host or trailing-slash normalisation. The one exception is a registered `http` URI on a
literal loopback host — `127.0.0.1` or `[::1]`, never `localhost` ([0.3 · 22]) — where the port,
and only the port, is ignored (RFC 8252 §7.3).

What a registration may hold is decided here too, at the owner's act, so an entry that could never
be safe — `localhost`, a fragment, plain `http` off loopback — is refused when the owner can read
the refusal, and never reaches `/authorize` to be refused there instead (§5.2 clause 1).
"""

from __future__ import annotations

from urllib.parse import urlsplit

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "[::1]"})


class RedirectURIRefused(ValueError):
    """A redirect URI the registry may not hold (§5, §5.2). Raised at registration only."""


def _split_loopback(uri: str) -> tuple[str, str, str] | None:
    """`(prefix, port, rest)` for an `http://<loopback>[:port]<rest>` URI, else None. Parsed by
    hand on the literal string so nothing is normalised on the way: the comparison stays bytewise
    on every component but the port."""
    scheme = "http://"
    if not uri.startswith(scheme):
        return None
    after = uri[len(scheme) :]
    for host in LOOPBACK_HOSTS:
        if after.startswith(host):
            tail = after[len(host) :]
            port = ""
            if tail.startswith(":"):
                end = len(tail)
                for i, ch in enumerate(tail[1:], start=1):
                    if not ch.isdigit():
                        end = i
                        break
                port, tail = tail[1:end], tail[end:]
                if not (port.isascii() and port.isdigit() and len(port) <= 5):
                    return None
                if not 0 < int(port) <= 65535:
                    return None
            if tail and tail[0] not in "/?":
                return None
            return scheme + host, port, tail
    return None


def matches(requested: str, registered: str) -> bool:
    """Whether a request's `redirect_uri` matches ONE registered entry (§5.1, §5.2)."""
    if not isinstance(requested, str) or not isinstance(registered, str):
        return False
    if requested == registered:
        return True
    reg = _split_loopback(registered)
    req = _split_loopback(requested)
    if reg is None or req is None:
        return False
    # Scheme, host and everything after the port compared exactly; only the port may differ.
    return reg[0] == req[0] and reg[2] == req[2]


def match_any(requested: str, registered: list[str]) -> bool:
    """Whether a request's `redirect_uri` matches any allowlist entry (§5.1). Every entry is
    compared, but no timing claim is made: §5.3 clause 2's budget is owed by the response."""
    found = False
    for entry in registered:
        found = matches(requested, entry) or found
    return found


def _ldh_host(host: str) -> str | None:
    """The host lowercased with one trailing dot stripped, if it is an ASCII LDH name (RFC 1123
    §2.1); else None. Admitting only this form refuses every spelling a resolver or a URL parser
    could turn into another name — percent-encoding, IDNA-mapped full-width letters, ideographic
    full stops — so the `localhost` test below sees the one spelling there is."""
    name = host.removesuffix(".")
    if not name or len(name) > 253 or not name.isascii():
        return None
    for label in name.split("."):
        if not 0 < len(label) <= 63 or "-" in (label[0], label[-1]):
            return None
        if not label.replace("-", "a").isalnum():  # ASCII already: letters, digits, hyphens
            return None
    return name.lower()


def check_registrable(uri: str) -> str:
    """Admit a redirect URI into a client entry, or refuse it (§5.1, §5.2, [0.3 · 22])."""
    if not isinstance(uri, str) or not uri or not uri.isprintable() or " " in uri or "\\" in uri:
        raise RedirectURIRefused("a redirect URI is one absolute URI")
    try:
        parts = urlsplit(uri)
        parts.port  # noqa: B018 — raises on a non-numeric or out-of-range port
    except ValueError as exc:
        raise RedirectURIRefused("a redirect URI is one absolute URI") from exc
    if "#" in uri:
        raise RedirectURIRefused("a registered redirect URI carries no fragment")
    if "@" in parts.netloc:
        raise RedirectURIRefused("a redirect URI carries no userinfo")
    # The host as written: `parts.hostname` lowercases and unbrackets, so read it off the netloc.
    raw_host = parts.netloc if parts.netloc.endswith("]") else parts.netloc.rsplit(":", 1)[0]
    name = _ldh_host(raw_host)
    if name is not None and (name == "localhost" or name.endswith(".localhost")):
        raise RedirectURIRefused("register http://127.0.0.1/… or http://[::1]/…, not localhost")
    if parts.scheme == "http" and _split_loopback(uri) is not None:
        return uri
    if parts.scheme == "https" and (raw_host in LOOPBACK_HOSTS or name is not None):
        return uri
    raise RedirectURIRefused("a redirect URI is https on an ASCII name, or http on a loopback IP")
