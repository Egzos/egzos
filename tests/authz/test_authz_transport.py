# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""§2 loopback bind (authz/transport.py)."""

from __future__ import annotations

import pytest

from egzos.authz import transport


@pytest.mark.parametrize("host", ["127.0.0.1", "127.255.0.9", "::1", "[::1]", " 127.0.0.1 "])
def test_plain_http_only_on_a_loopback_bind(host):
    assert transport.plain_http_allowed(host)


@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "::", "[::]", "192.168.1.4", "10.0.0.1", "localhost", "::ffff:127.0.0.1",
     "128.0.0.1", "", "fe80::1",
     "::1%lo", "127.1", "0177.0.0.1", "127.0.0.1:8443"],
)
def test_tls_required_on_every_other_bind(host):
    assert not transport.plain_http_allowed(host)
