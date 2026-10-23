# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The confirm (identity.md §5, rest.md §4.2–§4.3): how a person says yes to something that widens who
can see an item, and to every human-only act.

Two legs on one route. The first leg issues a challenge bound to this request — the principal, the
act, its subject and destination, and the audience delta — and shows who would newly see the item.
The second leg presents the challenge and a proof. As one transaction the challenge is spent
(confirmed or refused alike, so a refusal never leaves a challenge to retry), its binding checked,
and the proof verified; the act lands in the same transaction. Every concluded proof is a
`step_up` entry, with `details.proof` and, for a refusal, `details.reason`.

Two proofs. `biometric`: a WebAuthn assertion with user verification from a credential the person
registered here (Face ID, Touch ID, Windows Hello), verified by the maintained `webauthn` library
against the stored public key. `button`: an explicit confirm, only for a person with no registered
credential, and only where `confirm.allow_button` is on — once a person has a credential, every
confirm of theirs needs it, so a stolen session cannot fall back to the button.

A credential belongs to a relying party: the browser origin it was made on (`egzos.io`, a fork's
UI). The door passes the request's `Origin` only when it is one of `identity.browser_origins`, so an
assertion made on any other origin never verifies.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from egzos._ids import ulid
from egzos._types import ConfirmChallenge, ConfirmCredential, ConfirmState
from egzos.identity import SKEW_SECONDS
from egzos.ledger import Ledger
from egzos.model import Token, now_iso

#: rest.md §4.2 item 5: a challenge lives `step_up.window_seconds`, never less than this.
MIN_CHALLENGE_SECONDS = 60
#: How long an expired challenge is kept, so a late second leg still reads `spent` or `stale`.
CHALLENGE_KEEP_SECONDS = 86400
#: rest.md §4.3: how old a sign-in may be where an act needs a fresh one.
FRESH_SIGN_IN_SECONDS = 300
PROOFS = ("biometric", "button")
#: rest.md §4.2 item 4's closed reasons.
REASONS = ("stale", "spent", "foreign", "mismatch", "assertion", "button_off", "delta_changed",
           "not_fresh")
RP_NAME = "egzos"
#: rest.md §4.3's closed reasons, from the confirm's own (`REASONS`): an add's, and a removal's.
ADD_REASONS = {"button_off": "button_refused", "assertion": "no_proof"}
REMOVE_REASONS = {"button_off": "button_refused", "assertion": "assertion"}
CREDENTIAL_NAME_MAX = 64


def _iso(ts: float) -> str:
    """Fixed width, microseconds always written, so two of these compare as the times they are
    (a1r on #289: `isoformat` drops a zero fraction, and `Z` sorts after `.`)."""
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _epoch(text: str) -> float:
    return datetime.fromisoformat(text).timestamp()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def rp_of(origin: str | None) -> str | None:
    return urlsplit(origin).hostname if origin else None


def person_of(token: Token) -> str:
    """Whose credentials a confirm draws on: the interactive principal's owner — `user:<sub>` for
    a provider sign-in, the owner token's owner for the container's own."""
    return token.owner


class Confirm:
    def __init__(
        self,
        state: ConfirmState,
        ledger: Ledger,
        config: Callable[[str], Any],
        *,
        window_seconds: Callable[[], int],
        clock: Callable[[], float] = time.time,
        salt: Callable[[], str] = lambda: "",
    ):
        self.state = state
        self.ledger = ledger
        self.config = config
        self.window_seconds = window_seconds
        self.clock = clock
        # Per container: what a person's WebAuthn user handle is derived with.
        self.salt = salt

    # -- credentials ------------------------------------------------------------------------------
    def credentials(self, person: str, rp_id: str | None = None) -> list[ConfirmCredential]:
        return [
            c for c in self.state.list_credentials(person)
            if not c["removed"] and (rp_id is None or c["rp_id"] == rp_id)
        ]

    def _request_options(self, person: str, rp_id: str | None, challenge: str) -> Any:
        creds = self.credentials(person, rp_id) if rp_id else []
        if not creds:
            return None  # rest.md §4.2 item 7: no credential here, so no assertion is possible
        options = generate_authentication_options(
            rp_id=rp_id,
            challenge=challenge.encode(),
            allow_credentials=[
                PublicKeyCredentialDescriptor(id=_unb64(c["credential_id"])) for c in creds
            ],
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        return json.loads(options_to_json(options))

    def _challenge(self, token: Token, *, act: str, subject: str, destination: str | None,
                   delta: list[str]) -> ConfirmChallenge:
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
            "expires_at": _iso(self.clock() + lifetime),
        }
        self.state.put_challenge(challenge)
        return challenge

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
        origin: str | None = None,
    ) -> dict[str, Any]:
        """A fresh challenge for this exact request, and the answer the first leg carries. The
        caller appends the first leg's `context.fetch`: showing `newly` is a read."""
        challenge = self._challenge(token, act=act, subject=subject, destination=destination,
                                    delta=delta)
        return {
            "result": "confirm",
            "newly": newly,
            "challenge": challenge["id"],
            "webauthn": self._request_options(person_of(token), rp_of(origin), challenge["id"]),
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
        origin: str | None = None,
        biometric_only: bool = False,
        fresh_sign_in: bool = False,
    ) -> str | None:
        """Spend the presented challenge and judge the proof. `None` is confirmed; otherwise the
        reason it was refused. Either way one `step_up` is appended. Run it inside the act's own
        transaction, so a confirmed proof and the act it confirms land together. `fresh_sign_in`:
        the button also needs a fresh sign-in (rest.md §4.3); a biometric never does."""
        if not isinstance(presented, dict) or presented.get("proof") not in PROOFS:
            raise ValueError("confirm needs a challenge and a proof")
        challenge_id = presented.get("challenge")
        if not isinstance(challenge_id, str) or not challenge_id:
            raise ValueError("confirm needs a challenge and a proof")
        proof = presented["proof"]
        reason = self._judge(token, challenge_id, presented, act=act, subject=subject,
                             destination=destination, delta=delta, origin=origin,
                             biometric_only=biometric_only, fresh_sign_in=fresh_sign_in)
        details: dict[str, Any] = {"via": "confirm", "act": act, "proof": proof,
                                   "outcome": "refused" if reason else "confirmed"}
        if reason:
            details["reason"] = reason
        self.ledger.append("step_up", actor=token.owner, principal=token.principal,
                           subject=subject, **details)
        return reason

    def _judge(self, token: Token, challenge_id: str, presented: dict[str, Any], *, act: str,
               subject: str, destination: str | None, delta: list[str], origin: str | None,
               biometric_only: bool, fresh_sign_in: bool) -> str | None:
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
        person = person_of(token)
        if presented["proof"] == "button":
            # Off by config, off for a person who has registered a credential (identity.md §5),
            # and off for the acts that take a biometric only (removing a credential).
            if biometric_only or not self.config("confirm.allow_button"):
                return "button_off"
            if self.credentials(person):
                return "button_off"
            if fresh_sign_in and not self.fresh(token):
                return "not_fresh"
            return None
        return self._assert(person, presented.get("assertion"), challenge_id, origin)

    def fresh(self, token: Token) -> bool:
        """rest.md §4.3's fresh sign-in: the provider token's newest `amr` time at most
        `FRESH_SIGN_IN_SECONDS` old, and not ahead of this clock by more than check 4's skew. A
        container `Token` carries no sign-in, so it is never fresh (a1r on #290)."""
        signed_in = getattr(token, "auth_time", None)
        return signed_in is not None and (
            -SKEW_SECONDS <= self.clock() - signed_in <= FRESH_SIGN_IN_SECONDS)

    def _assert(self, person: str, assertion: Any, challenge_id: str,
                origin: str | None) -> str | None:
        rp_id = rp_of(origin)
        if not isinstance(assertion, dict) or rp_id is None:
            return "assertion"
        raw_id = assertion.get("id")
        match = next((c for c in self.credentials(person, rp_id)
                      if c["credential_id"] == raw_id), None)
        if match is None:
            return "assertion"
        try:
            verified = verify_authentication_response(
                credential=assertion,
                expected_challenge=challenge_id.encode(),
                expected_rp_id=rp_id,
                expected_origin=origin,
                credential_public_key=_unb64(match["public_key"]),
                credential_current_sign_count=match["sign_count"],
                require_user_verification=True,
            )
        except Exception:  # noqa: BLE001 — any verification failure is one reason, no detail
            return "assertion"
        self.state.put_credential({**match, "sign_count": verified.new_sign_count,
                                   "last_used": now_iso()})
        return None

    def last_step_up_seq(self) -> int | None:
        tail = self.ledger.tail(1)
        return tail[-1]["seq"] if tail else None

    # -- registration (rest.md §4.3) --------------------------------------------------------------
    def begin_registration(self, token: Token, *, origin: str, name: str) -> dict[str, Any]:
        """The registration's first leg: creation options under a challenge bound to this person
        and relying party, and, for a person who already has a credential, the assertion's own
        challenge (an existing credential must agree to a new one)."""
        person, rp_id = person_of(token), rp_of(origin)
        challenge = self._challenge(token, act="register", subject=person, destination=rp_id,
                                    delta=[])
        existing = self.credentials(person, rp_id)
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name=RP_NAME,
            user_name=name,
            # Salted per container, so no two containers hand an authenticator the same handle
            # for one person (a1r on #290).
            user_id=hashlib.sha256(f"{self.salt()}|{person}".encode()).digest()[:32],
            user_display_name=name,
            challenge=challenge["id"].encode(),
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
            exclude_credentials=[
                PublicKeyCredentialDescriptor(id=_unb64(c["credential_id"])) for c in existing
            ],
        )
        out: dict[str, Any] = {
            "result": "register",
            "challenge": challenge["id"],
            "webauthn": json.loads(options_to_json(options)),
            "expires_at": challenge["expires_at"],
        }
        # The proof the second leg carries: an existing credential's biometric, whose options
        # list the person's credentials, or for a first credential the button (`webauthn` null).
        agree = self._challenge(token, act="credential.add", subject=person, destination=rp_id,
                                delta=[])
        out["confirm"] = {
            "challenge": agree["id"],
            "webauthn": self._request_options(person, rp_id, agree["id"]),
        }
        return out

    def finish_registration(
        self,
        token: Token,
        *,
        origin: str,
        challenge_id: str,
        attestation: Any,
        presented: Any,
        name: str,
        fresh: bool,
        owner_surface: bool,
    ) -> tuple[ConfirmCredential | None, str | None]:
        """The second leg: the proof first (an existing credential's biometric, or for a first
        credential the button and a fresh sign-in), then the attestation. Returns the stored
        credential, or the reason it was refused; `identity.credential` records which."""
        person, rp_id = person_of(token), rp_of(origin)
        reason = self._add_proof(token, presented, person=person, rp_id=rp_id, origin=origin,
                                 fresh=fresh, owner_surface=owner_surface)
        credential: ConfirmCredential | None = None
        if reason is None:
            record = self.state.spend_challenge(challenge_id)
            if record is None or _epoch(record["expires_at"]) <= self.clock():
                reason = "stale"
            elif record.get("spent"):
                reason = "stale"
            elif (record["principal"], record["act"], record["subject"], record["destination"]) != (
                token.id, "register", person, rp_id
            ):
                reason = "stale"
            else:
                credential, reason = self._attest(person, rp_id, origin, challenge_id,
                                                  attestation, name)
        details: dict[str, Any] = {"op": "add", "outcome": "refused" if reason else "added"}
        if reason:
            details["reason"] = reason
        else:
            details["credential"] = credential["id"]
        self.ledger.append("identity.credential", actor=token.owner, principal=token.principal,
                           subject=person, **details)
        return credential, reason

    def _add_proof(self, token: Token, presented: Any, *, person: str, rp_id: str | None,
                   origin: str, fresh: bool, owner_surface: bool) -> str | None:
        """rest.md §4.3: a person with a credential adds another only with a biometric proof from
        an existing one; a first credential needs the button and a fresh sign-in, or, where
        buttons are off, the owner's own surface (the lifeboat or the CLI with the owner `Token`;
        never the REST door). Every proof presented is concluded, so it leaves its `step_up`."""
        existing = bool(self.credentials(person))
        if not existing and not self.config("confirm.allow_button") and owner_surface:
            return None  # buttons off: the owner's own surface, which presents no proof
        if not isinstance(presented, dict):
            return "no_proof"
        reason = self.conclude(token, presented, act="credential.add", subject=person,
                               destination=rp_id, delta=[], origin=origin,
                               biometric_only=existing)
        if reason is not None:
            return ADD_REASONS.get(reason, "stale")
        if not existing and not (fresh or owner_surface):
            return "not_fresh"
        return None

    def _attest(self, person: str, rp_id: str, origin: str, challenge_id: str, attestation: Any,
                name: str) -> tuple[ConfirmCredential | None, str | None]:
        if not isinstance(attestation, dict):
            return None, "attestation"
        try:
            verified = verify_registration_response(
                credential=attestation,
                expected_challenge=challenge_id.encode(),
                expected_rp_id=rp_id,
                expected_origin=origin,
                require_user_verification=True,
            )
        except Exception:  # noqa: BLE001 — any verification failure is one reason, no detail
            return None, "attestation"
        credential: ConfirmCredential = {
            "id": ulid(),
            "person": person,
            "credential_id": _b64(verified.credential_id),
            "public_key": _b64(verified.credential_public_key),
            "sign_count": verified.sign_count,
            "rp_id": rp_id,
            "name": name,
            "created_at": now_iso(),
            "last_used": None,
            "removed": False,
        }
        self.state.put_credential(credential)
        return credential, None

    def remove(self, token: Token, credential: ConfirmCredential) -> None:
        """Mark a credential removed and record it (`identity.credential`, `op: remove`). The
        caller has judged the biometric proof, or holds the owner token (the recovery path)."""
        self.state.put_credential({**credential, "removed": True})
        self.ledger.append("identity.credential", actor=token.owner, principal=token.principal,
                           subject=credential["person"], op="remove", outcome="removed",
                           credential=credential["id"])
