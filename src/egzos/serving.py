# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""What this door serves (rest.md §4.6): `GET /v1/limits` and `egzos_limits` read it here, so the
two answer alike and append the same read. It is a read of config keys and constants: it sets
nothing and serves no other key."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from egzos._types import CONTRACT_VERSION, DoorFeature
from egzos.model import Token
from egzos.store.uploads import MAX_HELD

if TYPE_CHECKING:
    from egzos.container import Container

#: rest.md §4.6: the words `GET /v1/limits` names, each only once its code runs here and every
#: condition §4.6 sets for it holds. `items.rename` and `scopes.rename` wait on their routes;
#: `grants.own` is named with the read it names, which lands after every rule it needs (§4.3).
FEATURES: tuple[DoorFeature, ...] = ("terminals.machine", "grants.own")


def limits(c: Container, token: Token) -> dict[str, Any]:
    """To any valid token, a `client` principal's included: facts about the caller's own
    container and no secret. Reading it appends one `context.fetch` with `read: limits`."""
    c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                    client=token.client, read="limits", items=[], layers=[], withheld=0)
    return {
        "contract": CONTRACT_VERSION,
        "features": list(FEATURES),
        "upload_max_bytes": c.config_value("blobs.upload_max_bytes"),
        "inline_max_bytes": c.config_value("blobs.inline_max_bytes"),
        "uploads_held_max": MAX_HELD,
    }
