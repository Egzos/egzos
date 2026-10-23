# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
`BlobGrant` redemption at the REST door (rest.md §6): `GET /v1/blobs/<sha256>?item=&token=
&expires_at=&sig=`.

The descriptor is the whole credential, so no `Authorization` header is read. The eight checks run
in the contract's order, and every failure is §3's one refusal, whichever check it was. A
descriptor that does not verify names no caller: the throttle counts it, and the window's
`rest.tally` tallies it under `forged`. One that verifies is its token's: that token's bucket is
read before check 3, and a refusal from check 3 on counts in it and appends `context.fetch` with
the check, attributed to the token. Check 4 spends the grant, so a later refusal still spends it.
"""

from __future__ import annotations

import re
from typing import Any

from egzos._ids import is_ulid
from egzos._types import BLOB_GRANT_LIFETIME_SECONDS, BlobGrant
from egzos.api.throttle import Throttle
from egzos.container import Container
from egzos.ledger import acting_for
from egzos.store.blobs import GRANT_QUERY, _is_digest
from egzos.trust import grant_expiry

#: §6: the headers the bytes go out under, and no others: never rendered on this origin.
PULL_HEADERS = {
    "Content-Type": "application/octet-stream",
    "Content-Disposition": "attachment",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "sandbox",
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
}
#: A `Token.id`, or a provider grant's `user:<sub>` or `agent:<client_id>:<sub>`.
_TOKEN = re.compile(r"[\x21-\x7e]{1,512}")
_SIG = re.compile(r"[0-9a-f]{64}")


def descriptor(sha256: str, params: Any) -> BlobGrant | None:
    """Check 1: the path's digest, and the four parameters, each once and well-formed."""
    if set(params.keys()) != set(GRANT_QUERY) or len(params.multi_items()) != len(GRANT_QUERY):
        return None
    grant: BlobGrant = {"sha256": sha256, "item": params["item"], "token": params["token"],
                        "expires_at": params["expires_at"], "sig": params["sig"]}
    if (_is_digest(sha256) and is_ulid(grant["item"]) and _TOKEN.fullmatch(grant["token"])
            and _SIG.fullmatch(grant["sig"]) and grant_expiry(grant["expires_at"]) is not None):
        return grant
    return None


def redeem(
    c: Container, throttle: Throttle, address: str | None, sha256: str, params: Any
) -> bytes | None:
    """The bytes a descriptor redeems, or None for §3's refusal."""
    grant = descriptor(sha256, params)                                      # 1
    if grant is None or not c.trust.verify_grant(grant):                    # 2
        throttle.count(address, refused=False, forged=True)
        return None
    if throttle.token_holds(grant["token"]):
        # §2 item 7: counted and not evaluated, so neither spent nor traced; its release is.
        throttle.count_token(grant["token"], refused=True)
        return None
    # The token as it stands now: never None, as an id no record holds is a revoked stand-in.
    token, item, data = c.trust.named(grant["token"]), None, None
    expires = grant_expiry(grant["expires_at"]) or 0.0
    if expires <= c.trust.clock():                                          # 3
        failed: int | None = 3
    elif not c.trust.spend_grant(grant):                                    # 4
        failed = 4
    else:
        item = c.store.get(grant["item"])
        failed = c.trust.pull_refusal(                                      # 5, 6
            token, item, minted=expires - BLOB_GRANT_LIFETIME_SECONDS)
        # 7: the path's digest is the descriptor's own (check 1 read it there).
        if failed is None and grant["sha256"] != item.content.get("sha256"):
            failed = 7
        if failed is None and (data := c.blobs.get(sha256)) is None:
            failed = 8
    with acting_for(getattr(token, "acting_for", None)):
        if failed is not None:
            throttle.count_token(grant["token"], refused=False)
            c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                            client=token.client, ref=grant["item"], token=grant["token"],
                            check=failed, items=[], layers=[], withheld=0)
            return None
        c.ledger.append("blob.pull", actor=token.owner, principal=token.principal,
                        subject=item.id, scope=item.scope, sha256=sha256, size=len(data))
    return data
