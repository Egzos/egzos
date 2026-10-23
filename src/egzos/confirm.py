# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The confirm (identity.md §5, rest.md §4.2): how a person says yes to something that widens who can
see an item, and to every human-only act.

Two legs on one route. The first leg issues a challenge bound to this request — the principal, the
act, its subject and destination, and the audience delta — and shows who would newly see the item.
The second leg presents the challenge and a proof. As one transaction the challenge is spent
(confirmed or refused alike, so a refusal never leaves a challenge to retry), its binding checked,
and the proof verified; the act lands in the same transaction. Every concluded proof is a
`step_up` entry, with `details.proof` and, for a refusal, `details.reason`.

Two proofs: `biometric`, a WebAuthn assertion with user verification from a credential the person
registered here (Face ID, Touch ID, Windows Hello), and `button`, for a person with no registered
credential, where `confirm.allow_button` is on. No credential can be registered yet, so `webauthn`
is `null` and the button is the proof that runs; a `biometric` proof is refused (`assertion`) until
credentials land (rest.md §4.3). A `client` principal never gets here: its widening act parks.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from egzos._types import ConfirmChallenge, ConfirmState
from egzos.ledger import Ledger
from egzos.model import Token

#: rest.md §4.2 item 5: a challenge lives `step_up.window_seconds`, never less than this.
MIN_CHALLENGE_SECONDS = 60
#: How long an expired challenge is kept, so a late second leg still reads `spent` or `stale`.
CHALLENGE_KEEP_SECONDS = 86400
PROOFS = ("biometric", "button")
#: rest.md §4.2 item 4's closed reasons.
REASONS = ("stale", "spent", "foreign", "mismatch", "assertion", "button_off", "delta_changed")


def _iso(ts: float) -> str:
    """Fixed width, microseconds always written, so two of these compare as the times they are
    (a1r on #289: `isoformat` drops a zero fraction, and `Z` sorts after `.`)."""
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _epoch(text: str) -> float:
    return datetime.fromisoformat(text).timestamp()


class Confirm:
    def __init__(
        self,
        state: ConfirmState,
        ledger: Ledger,
        config: Callable[[str], Any],
        *,
        window_seconds: Callable[[], int],
        clock: Callable[[], float] = time.time,
    ):
        self.state = state
        self.ledger = ledger
        self.config = config
        self.window_seconds = window_seconds
        self.clock = clock

    # -- the first leg ----------------------------------------------------------------------------
    def issue(
        self,
        token: Token,
        *,
        act: str,
        subject: str,
        destination: str | None,
        delta: list[str],
        newly: list[str],
    ) -> dict[str, Any]:
        """A fresh challenge for this exact request, and the answer the first leg carries. The
        caller appends the first leg's `context.fetch`: showing `newly` is a read."""
        now = self.clock()
        lifetime = max(MIN_CHALLENGE_SECONDS, self.window_seconds())
        # A day after it expired a challenge only answers `stale`; forget it (a1r on #289).
        self.state.forget_challenges(_iso(self.clock() - CHALLENGE_KEEP_SECONDS))
        challenge: ConfirmChallenge = {
            "id": secrets.token_urlsafe(32),
            "principal": token.id,
            "act": act,
            "subject": subject,
            "destination": destination,
            "delta": sorted(delta),
            "expires_at": _iso(now + lifetime),
        }
        self.state.put_challenge(challenge)
        return {
            "result": "confirm",
            "newly": newly,
            "challenge": challenge["id"],
            "webauthn": None,  # rest.md §4.2 item 7: no credential is registered here yet
            "expires_at": challenge["expires_at"],
        }

    # -- the second leg ---------------------------------------------------------------------------
    def conclude(
        self,
        token: Token,
        presented: Any,
        *,
        act: str,
        subject: str,
        destination: str | None,
        delta: list[str],
    ) -> str | None:
        """Spend the presented challenge and judge the proof. `None` is confirmed; otherwise the
        reason it was refused. Either way one `step_up` is appended. Run it inside the act's own
        transaction, so a confirmed proof and the act it confirms land together."""
        if not isinstance(presented, dict) or presented.get("proof") not in PROOFS:
            raise ValueError("confirm needs a challenge and a proof")
        challenge_id = presented.get("challenge")
        if not isinstance(challenge_id, str) or not challenge_id:
            raise ValueError("confirm needs a challenge and a proof")
        proof = presented["proof"]
        reason = self._judge(token, challenge_id, proof, presented, act=act, subject=subject,
                             destination=destination, delta=delta)
        details: dict[str, Any] = {"via": "confirm", "act": act, "proof": proof,
                                   "outcome": "refused" if reason else "confirmed"}
        if reason:
            details["reason"] = reason
        self.ledger.append("step_up", actor=token.owner, principal=token.principal,
                           subject=subject, **details)
        return reason

    def _judge(self, token, challenge_id, proof, presented, *, act, subject, destination, delta):
        record = self.state.spend_challenge(challenge_id)  # spent now, whatever is decided below
        if record is None:
            return "stale"
        if record.get("spent"):
            return "spent"
        if _epoch(record["expires_at"]) <= self.clock():
            return "stale"
        if record["principal"] != token.id:
            return "foreign"
        if (record["act"], record["subject"], record["destination"]) != (act, subject, destination):
            return "mismatch"
        if record["delta"] != sorted(delta):
            return "delta_changed"
        if proof == "button":
            if not self.config("confirm.allow_button"):
                return "button_off"
            return None
        # `biometric`: no credential can be registered yet (rest.md §4.3 lands next), so no
        # assertion verifies.
        return "assertion"

    def last_step_up_seq(self) -> int | None:
        tail = self.ledger.tail(1)
        return tail[-1]["seq"] if tail else None
