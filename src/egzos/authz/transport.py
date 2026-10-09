# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The loopback exemption from TLS (authorization-server.md §2, [0.3 · 9]).

Plain HTTP is allowed only when the listening socket is bound to `127.0.0.0/8` or `::1`. The
decision takes the BIND address the listener holds — never a request, a `Host`, or a forwarded
header (`X-Forwarded-For`, `Forwarded`, `X-Forwarded-Proto`), all attacker-supplied by
construction. `0.0.0.0`, `::` and every LAN address require TLS, and so does a loopback listener
behind a tunnel or proxy — which this function cannot see, so a caller fronting one must not ask
it. Enforcing the refusal at `serve` is a3-doorman's; this is the rule it enforces.
"""

from __future__ import annotations

import ipaddress


def plain_http_allowed(bind_host: str) -> bool:
    """Whether an AS listener bound to `bind_host` may serve without TLS.

    `bind_host` is an IP literal (brackets allowed for IPv6). A hostname — `localhost` included —
    is refused: a name is something a resolver can move, and the socket's address is what binds."""
    host = bind_host.strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        # `::1` only. An IPv4-mapped `::ffff:127.0.0.1` is not among the addresses [0.3 · 9]
        # names, so it takes the stricter reading: TLS.
        return address == ipaddress.IPv6Address("::1")
    return address in ipaddress.ip_network("127.0.0.0/8")
