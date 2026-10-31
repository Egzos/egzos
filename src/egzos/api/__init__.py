# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The REST door (`egzos serve --http`; spec/contracts/rest.md): an HTTP resource server, in-process
with the container, under `/v1/`. It accepts the container's own `Token` and access tokens from
the container's identity provider (`identity.md`), and is where egzos.io and any fork's UI read
and write the person's container.

TLS (rest.md §1): plain HTTP only when the listening socket is bound to loopback, decided from the
socket and never from a forwarded header. Anywhere else the door serves TLS, or does not start.
Behind a TLS-terminating proxy on loopback every caller arrives from the proxy's address, so the
throttle's per-source bucket (rest.md §2 item 7) counts the proxy as one source: the container-
global bucket still bounds a sweep, and a proxy that throttles per client is the place to split
callers apart. A forwarded header is never read to do it here.

The origin `/mcp`'s protected-resource metadata names (identity.md §7) is `identity.origin`, the
one clients reach (§2), when the owner sets it, as behind a proxy or on a wildcard address. Absent,
it is the one `serve` binds: the socket's scheme, host and port. Never a request's `Host` or a
forwarded header, so the document is the same for every caller.
"""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

from egzos.container import Container

DEFAULT_PORT = 7426
#: The host setting that opts a container into plain HTTP behind its host's TLS-terminating proxy.
EDGE_PROXY = "EGZOS_EDGE_PROXY"
#: Not globally routable: private, loopback, link-local and unique-local (fc00::/7 holds Fly's
#: fdaa::/16 6PN). Anything else is treated as routable, so an address in doubt refuses.
_NOT_ROUTABLE = tuple(ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "169.254.0.0/16",
    "::1/128", "fe80::/10", "fc00::/7",
))


def loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def bound_origin(host: str, port: int, *, tls: bool) -> str:
    """The origin a door bound to `host:port` serves: `https` when it holds TLS, a default port
    left out, an IPv6 address in brackets."""
    scheme = "https" if tls else "http"
    name = f"[{host}]" if ":" in host else host
    return f"{scheme}://{name}" if port == (443 if tls else 80) else f"{scheme}://{name}:{port}"


def edge_proxy(environ: Mapping[str, str] | None = None) -> bool:
    """Whether the host opted in to TLS at its edge: `EGZOS_EDGE_PROXY=1`, and nothing else."""
    value = (os.environ if environ is None else environ).get(EDGE_PROXY)
    if value is None:
        return False
    if value != "1":
        raise ValueError(f"{EDGE_PROXY}: 1, or unset")
    return True


def globally_routable(address: str) -> bool:
    """Whether `address` (an IP literal, IPv6 with or without a zone) is globally routable: any
    address outside `_NOT_ROUTABLE`, an IPv4-mapped IPv6 address judged as its IPv4."""
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.is_unspecified:
        return False
    return not any(ip.version == n.version and ip in n for n in _NOT_ROUTABLE)


def check_edge(container: Container, host: str) -> None:
    """Refuse (`PermissionError`) a plain-HTTP door at a host's edge unless the socket binds no
    globally routable address and is no unspecified address, and
    `identity.origin` is set explicitly with scheme `https` (rest.md §1)."""
    try:
        ip = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        raise PermissionError(
            f"{EDGE_PROXY}: bind an address, not a name, so the socket decides (rest.md §1)"
        ) from None
    if ip.is_unspecified:  # a host's own address list can be incomplete, so no list decides
        raise PermissionError(
            f"{EDGE_PROXY}: {host} binds every address; bind the host's private address itself"
        )
    if globally_routable(host):
        raise PermissionError(f"{EDGE_PROXY}: {host} is globally routable; bind a private address")
    origin = container.config_value("identity.origin")
    parsed = urlsplit(origin) if isinstance(origin, str) else None
    if parsed is None or parsed.scheme != "https" or not parsed.hostname:
        raise PermissionError(
            f"{EDGE_PROXY}: set identity.origin to the proxy's https origin "
            "(`egzos config set identity.origin https://…`)"
        )


def serve_http(
    container: Container,
    *,
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    tls_cert: Path | None = None,
    tls_key: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> None:
    import uvicorn

    from egzos.api.app import create_app

    if (tls_cert is None) != (tls_key is None):
        raise ValueError("TLS needs both a certificate and its key")
    edge = edge_proxy(environ)  # read first, so a mistyped value stops on every bind (a6 on #353)
    if tls_cert is None and not loopback(host) and edge:
        check_edge(container, host)
    elif tls_cert is None and not loopback(host):
        raise PermissionError(
            "plain HTTP is for a loopback socket only (rest.md §1): give --tls-cert and --tls-key, "
            "or bind 127.0.0.1 behind a TLS-terminating proxy"
        )
    origin = bound_origin(host, port, tls=tls_cert is not None)
    print(f"egzos REST door on {origin}/v1/, MCP on {origin}/mcp — Ctrl-C to stop.", flush=True)
    uvicorn.run(
        create_app(container, origin=origin),
        host=host,
        port=port,
        log_level="warning",
        access_log=False,  # a URL is not logged: the door's own record is the chain
        ssl_certfile=str(tls_cert) if tls_cert else None,
        ssl_keyfile=str(tls_key) if tls_key else None,
        proxy_headers=False,  # rest.md §1: the socket decides, never a forwarded header
        server_header=False,
    )
