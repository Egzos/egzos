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

The door's own origin, which `/mcp`'s protected-resource metadata names (identity.md §7), is the
one `serve` binds: the socket's scheme, host and port, never a request's `Host` or a forwarded
header, so the document is the same for every caller. Behind a proxy, or on a wildcard address,
that is not the origin clients reach; no contract key names that origin yet.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path

from egzos.container import Container

DEFAULT_PORT = 7426


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


def serve_http(
    container: Container,
    *,
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    tls_cert: Path | None = None,
    tls_key: Path | None = None,
) -> None:
    import uvicorn

    from egzos.api.app import create_app

    if (tls_cert is None) != (tls_key is None):
        raise ValueError("TLS needs both a certificate and its key")
    if tls_cert is None and not loopback(host):
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
