# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §4.4 item 2a: Trust signs an upload's address, HMAC-SHA256 under §6's key over
`canonical` JSON of `{"use": "upload", "upload", "opener", "size", "sha256", "expires_at"}`; it
lives 900 seconds and none is issued for an upload with less left; it is bound to its opener; "no
grant's `sig` verifies as an address and no address's as a grant"; and its spend is a record in
§6's spent records (storage.md §3.5), the sha256 of its `sig`, once."""

from __future__ import annotations

import hashlib
import hmac
from urllib.parse import parse_qsl, urlsplit

import pytest

from egzos._types import UPLOAD_ADDRESS_LIFETIME_SECONDS, BlobGrant, UploadAddress
from egzos.container import OWNER, Container
from egzos.model import canonical
from egzos.store.blobs import put_url
from egzos.trust import GRANT_KEY_FILE, TrustEngine, _utc

KW = {"actor": OWNER, "principal": "interactive"}
T0 = 1_900_000_000  # a whole second, so the upload's own expiry (written to the second) is exact
SHA = "ab" * 32


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path / "home")
    box.owner = box.init()
    box.p = box.nodes.create("project", "p", box.nodes.user_root(), token=box.owner, **KW)
    box.bot = _client(box, "contributor")
    box.uploads.clock = box.trust.clock = lambda: T0
    return box


def _client(c, role):
    return c.auth.mint(principal="client", owner="bot", client="probe", role=role, scopes=["*"],
                       actor=OWNER, by_principal="interactive")


def _open(c, token=None, size=1234):
    return c.uploads.open(token or c.bot, scope=c.p, name="a.bin", mime="application/pdf",
                          size=size, sha256=SHA)


def _key(c) -> bytes:
    return c.trust.grant_key()  # made at first need, as the container wires it


def _hmac(key: bytes, message: dict) -> str:
    return hmac.new(key, canonical(message).encode(), hashlib.sha256).hexdigest()


def test_an_address_signs_its_six_fields_with_use_upload(c):
    record = _open(c)
    address = c.trust.address(record, c.bot)
    expires_at = _utc(T0 + UPLOAD_ADDRESS_LIFETIME_SECONDS)
    assert address == {"upload": record["id"], "opener": c.bot.id, "size": "1234",
                       "sha256": SHA, "expires_at": expires_at, "sig": address["sig"]}
    message = {"use": "upload", "upload": record["id"], "opener": c.bot.id, "size": "1234",
               "sha256": SHA, "expires_at": expires_at}
    assert address["sig"] == _hmac(_key(c), message)
    assert c.trust.verify_address(address)


def test_an_address_appends_nothing(c):
    record = _open(c)
    before = c.ledger.tail(1)
    assert c.trust.address(record, c.bot) is not None
    assert c.ledger.tail(1) == before


# -- domain separation: neither kind of descriptor verifies as the other ---------------------------
#: Overlapping values, ordinary and hostile: each is tried in every field the two kinds share.
VALUES = ["0", "1234", SHA, "upload", "use", 'x","use":"upload', '{"use":"upload"}', "a,b", ""]


@pytest.mark.parametrize("value", VALUES)
def test_no_grants_sig_verifies_as_an_address_and_no_addresss_as_a_grant(c, value):
    key, expires_at = _key(c), _utc(T0 + 300)
    grant: BlobGrant = {"sha256": value, "item": value, "token": value,
                        "expires_at": expires_at, "sig": ""}
    grant["sig"] = TrustEngine._sign(grant, key)  # the grant mint's own signer
    assert c.trust.verify_grant(grant)
    for size in ("0", "1234"):
        as_address: UploadAddress = {"upload": value, "opener": value, "size": size,
                                     "sha256": value, "expires_at": expires_at,
                                     "sig": grant["sig"]}
        assert not c.trust.verify_address(as_address)

    address: UploadAddress = {"upload": value, "opener": value, "size": "0", "sha256": value,
                              "expires_at": expires_at, "sig": ""}
    address["sig"] = c.trust._sign_address(address, key)
    assert c.trust.verify_address(address)
    as_grant: BlobGrant = {"sha256": value, "item": value, "token": value,
                           "expires_at": expires_at, "sig": address["sig"]}
    assert not c.trust.verify_grant(as_grant)
    # Nor with the address's own fields, `use` and all, handed over as a grant.
    whole = {"use": "upload", **address}
    assert _hmac(key, {k: v for k, v in whole.items() if k != "sig"}) == address["sig"]
    assert not c.trust.verify_grant(whole)  # type: ignore[arg-type]


def test_a_grant_and_an_address_with_the_same_field_values_get_different_hmacs(c):
    record = _open(c)
    address = c.trust.address(record, c.bot)
    grant: BlobGrant = {"sha256": address["sha256"], "item": address["upload"],
                        "token": address["opener"], "expires_at": address["expires_at"], "sig": ""}
    assert TrustEngine._sign(grant, _key(c)) != address["sig"]


# -- one signature, one URL ----------------------------------------------------------------------
@pytest.mark.parametrize("size", ["01234", "+1234", " 1234", "1234 ", "1234\n", "1_234",
                                  "１２３４", "1234.0", "-0", ""])
def test_a_size_not_in_its_one_decimal_form_never_verifies_even_when_signed(c, size):
    address = c.trust.address(_open(c), c.bot)
    odd: UploadAddress = {**address, "size": size}
    odd["sig"] = c.trust._sign_address(odd, _key(c))
    assert not c.trust.verify_address(odd)


def test_an_address_of_other_fields_or_values_never_verifies(c):
    address = c.trust.address(_open(c), c.bot)
    assert not c.trust.verify_address({**address, "use": "upload"})  # type: ignore[typeddict-unknown-key]
    assert not c.trust.verify_address({**address, "size": 1234})  # type: ignore[typeddict-item]
    for field in ("upload", "opener", "sha256", "expires_at"):
        assert not c.trust.verify_address({**address, field: address[field] + "0"})
        assert not c.trust.verify_address({**address, field: address[field] + "\ud800"})


# -- issue -------------------------------------------------------------------------------------
def test_an_address_lives_900_seconds_and_none_is_issued_with_less_left_on_the_upload(c):
    record = _open(c)  # live for an hour from T0
    last = T0 + 3600 - UPLOAD_ADDRESS_LIFETIME_SECONDS
    c.trust.clock = lambda: last
    address = c.trust.address(record, c.bot)
    assert address["expires_at"] == _utc(T0 + 3600)  # no later than the upload's own end
    c.trust.clock = lambda: last + 0.001
    assert c.trust.address(record, c.bot) is None


def test_only_the_opener_holding_remember_on_a_waiting_upload_is_given_an_address(c):
    record = _open(c)
    assert c.trust.address(record, _client(c, "contributor")) is None  # not its opener
    assert c.trust.address(record, c.owner) is None
    assert c.trust.address({**record, "discarded": True}, c.bot) is None
    assert c.trust.address({**record, "staged": True}, c.bot) is None
    reader = _client(c, "reader")
    assert c.trust.address(_open(c, reader), reader) is None  # no `remember`
    assert c.trust.address(record, c.bot) is not None


def test_a_key_that_is_not_32_bytes_issues_no_address(c):
    record = _open(c)
    earlier = c.trust.address(record, c.bot)
    (c.home / GRANT_KEY_FILE).write_bytes(b"k" * 31)
    assert c.trust.address(record, c.bot) is None
    assert not c.trust.verify_address(earlier)


def test_a_rotated_key_fails_an_outstanding_address(c):
    record = _open(c)
    earlier = c.trust.address(record, c.bot)
    (c.home / GRANT_KEY_FILE).unlink()  # the owner's rotation until `egzos blob rotate` runs
    fresh = c.trust.address(record, c.bot)  # the next address makes a new key
    assert not c.trust.verify_address(earlier) and c.trust.verify_address(fresh)
    assert fresh["sig"] != earlier["sig"]


# -- spend -------------------------------------------------------------------------------------
def test_an_address_is_spent_once_and_a_second_spend_fails(c):
    address = c.trust.address(_open(c), c.bot)
    other = Container(c.home)  # a second process serving the same container
    assert c.trust.spend_address(address) is True
    assert other.trust.spend_address(address) is False
    assert c.trust.spend_address(address) is False
    digest = hashlib.sha256(address["sig"].encode()).hexdigest()
    rows = c.backend.db.execute("SELECT sig_hash, expires_at FROM spent_grants").fetchall()
    assert [tuple(r) for r in rows] == [(digest, address["expires_at"])]  # never the sig itself


def test_an_address_is_spent_outside_any_transaction(c):
    address = c.trust.address(_open(c), c.bot)
    with c.backend.atomic(), pytest.raises(RuntimeError):
        c.trust.spend_address(address)  # a rollback would unspend it
    assert c.trust.spend_address(address) is True  # the refused spend recorded nothing


def test_a_spent_address_is_kept_a_lifetime_past_its_expiry_whatever_mints_next(c, tmp_path):
    address = c.trust.address(_open(c), c.bot)
    assert c.trust.spend_address(address) is True
    ends = T0 + UPLOAD_ADDRESS_LIFETIME_SECONDS
    c.uploads.clock = c.trust.clock = lambda: ends + UPLOAD_ADDRESS_LIFETIME_SECONDS
    path = tmp_path / "g.bin"
    path.write_bytes(b"bytes")
    item = c.store.add(file=path, scope=c.p, token=c.owner, **KW)
    assert c.trust.authorize_pull(c.owner, item) is not None  # a grant's mint forgets older ones
    assert c.trust.address(_open(c), c.bot) is not None  # and so does an address's
    assert c.trust.spend_address(address) is False
    c.trust.clock = lambda: ends + UPLOAD_ADDRESS_LIFETIME_SECONDS + 1
    assert c.trust.address(_open(c), c.bot) is not None
    assert c.trust.spend_address(address) is True  # forgotten only past a lifetime


# -- the URL -------------------------------------------------------------------------------------
def test_put_url_percent_encodes_every_value_on_the_given_origin():
    address: UploadAddress = {"upload": "01J/x y", "opener": "agent:a&b=c", "size": "1234",
                              "sha256": SHA, "expires_at": "2030-03-17T17:46:40.000000Z",
                              "sig": "s+i/g?#"}
    url = put_url("https://box.example/", address)
    parts = urlsplit(url)
    assert (parts.scheme, parts.netloc, parts.path) == (
        "https", "box.example", "/v1/uploads/01J%2Fx%20y")
    assert parse_qsl(parts.query, strict_parsing=True) == [
        (k, address[k]) for k in ("opener", "size", "sha256", "expires_at", "sig")]
    assert "expires_at=2030-03-17T17:46:40.000000Z" in parts.query  # `:` as §6 writes it
    assert "use" not in dict(parse_qsl(parts.query))
