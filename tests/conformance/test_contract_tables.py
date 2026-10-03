# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The contract documents, read from disk, against `_types.py` (drift F24, issue #103).

`tests/_types/**` pins the code to literals transcribed into those tests — deliberately, so a test
cannot be fooled by asking the code what it contains. Nothing held the other half: **the documents
in `spec/contracts/` against either one.** F6, F8, F13 and F25 each survived in that gap, every one
a table or a count sentence that said one thing while the constant beside it said another.

Every expected value below is *parsed out of the markdown*; no contract text is transcribed here.
The literals this file carries are structural — section numbers, column names, and the row labels
of one table whose rows have no other name (`(a)`…`(f)`) — the addresses the contracts are cited
by everywhere else in the tree.

**Nothing here skips.** An unresolvable section number, a renamed column, a vanished fenced block,
a zero-row table — each is `pytest.fail`. A check that switches itself off when the thing it checks
is renamed is worse than no check, because the green tick keeps being reported. The `test_meta_*`
tests at the bottom hold that property by feeding the helpers a broken document.

Covered: `container.md` §8 (F6), `events.md` §1–§2 (F8), `context-item.md` §1–§5 (F13),
`authorization-server.md` §11.1, §12, §12.1 (F25), `storage.md` §1–§4.
"""

from __future__ import annotations

import re
import typing
from collections import Counter
from pathlib import Path

import pytest

import egzos._types as t

CONTRACTS = Path(__file__).resolve().parents[2] / "spec" / "contracts"

_WORDS = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty"
).split()
NUMBER_WORDS = {word: value for value, word in enumerate(_WORDS)}

_CODE = re.compile(r"`([^`\n]+)`")
_BRACE = re.compile(r"\{([^{}]*)\}")
_FENCE = re.compile(r"^```[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)
_SEP = re.compile(r"\s*[,·]\s*")
# A signature line in one of storage.md's fenced blocks. Anchored at column 0, so `query`'s wrapped
# continuation line is not mistaken for a second method.
_SIGNATURE = re.compile(r"^(\w+)\(", re.MULTILINE)
# `## 8 · …`, `### 11.1 · …`. The number is what the rest of the tree cites; the title is not.
# The trailing `[^\n]*` swallows the title, so a section's body starts below its heading and a
# heading such as ``## 2 · `kind` `` does not donate a code span to the first vocabulary parsed.
_HEADING = re.compile(r"^(#{2,6})[ \t]+(?:([\d.]+)[ \t]*·)?[^\n]*", re.MULTILINE)


# --- reading the documents ------------------------------------------------------------------
def doc(name: str) -> str:
    """One contract document. A missing file fails; it never skips the tests that read it."""
    path = CONTRACTS / name
    if not path.is_file():
        pytest.fail(f"{path} is missing — spec/contracts/{name} is what this suite checks against")
    return path.read_text(encoding="utf-8")


def plain(md: str) -> str:
    """Markdown emphasis and code ticks stripped, so prose patterns need not match around them."""
    return md.replace("**", "").replace("*", "").replace("`", "")


def section(md: str, number: str, *, where: str, nested: bool = True) -> str:
    """The body of the section numbered `number`, located by its number and not by its title.

    `nested=True` includes the subsections beneath it; `nested=False` stops at the next heading of
    any level, which is how to reach a section's own body when a subsection has a table too.
    """
    for match in _HEADING.finditer(md):
        if match.group(2) != number:
            continue
        level = len(match.group(1))
        start = match.end()
        for following in _HEADING.finditer(md, start):
            if not nested or len(following.group(1)) <= level:
                return md[start : following.start()]
        return md[start:]
    pytest.fail(f"{where}: no section numbered §{number} — the heading was renumbered or removed")


def fence(md: str, *, where: str) -> str:
    """The one fenced block in `md`. Zero or several is ambiguous, and ambiguity fails."""
    blocks = _FENCE.findall(md)
    if len(blocks) != 1:
        pytest.fail(f"{where}: expected exactly one fenced block, found {len(blocks)}")
    return blocks[0]


# --- markdown tables ------------------------------------------------------------------------
def _cells(line: str) -> list[str]:
    """One table row's cells. `\\|` inside a cell is an escaped pipe, not a column boundary."""
    line = line.strip()
    parts = re.split(r"(?<!\\)\|", line)
    if line.startswith("|"):
        parts = parts[1:]
    if line.endswith("|"):
        parts = parts[:-1]
    return [p.replace(r"\|", "|").strip() for p in parts]


def _is_rule(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c) for c in cells)


def tables(md: str) -> list[tuple[list[str], list[list[str]]]]:
    """Every pipe table in `md`, as `(header cells, body rows)`."""
    lines = md.splitlines()
    found = []
    i = 0
    while i < len(lines) - 1:
        if lines[i].lstrip().startswith("|") and _is_rule(_cells(lines[i + 1])):
            header = _cells(lines[i])
            rows = []
            i += 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            found.append((header, rows))
        else:
            i += 1
    return found


def table(md: str, *, columns: tuple[str, ...], where: str) -> list[list[str]]:
    """The rows of the one table in `md` whose header carries each of `columns` as a prefix.

    Matching the header, not the position, is what makes a renamed column a failure rather than a
    silent re-read of the wrong table.
    """
    matched = [
        (header, rows)
        for header, rows in tables(md)
        if all(any(plain(h).lower().startswith(c) for h in header) for c in columns)
    ]
    if len(matched) != 1:
        seen = [h for h, _ in tables(md)]
        pytest.fail(f"{where}: {len(matched)} tables have columns {columns}, not 1; saw {seen}")
    header, rows = matched[0]
    if not rows:
        pytest.fail(f"{where}: the table has no rows — a zero-row table passes nothing")
    width = len(header)
    for row in rows:
        if len(row) != width:
            pytest.fail(f"{where}: row {row} has {len(row)} cells against a header of {width}")
    return rows


# --- code spans, brace lists, counted prose ---------------------------------------------------
def anchor_end(md: str, anchor: str | None, *, where: str) -> int:
    """Where `anchor` ends in `md`, tolerating line wraps. The documents wrap at 100 columns, so a
    literal `str.find` for a two-word anchor is a coin toss on where the paragraph broke."""
    if anchor is None:
        return 0
    match = re.search(r"\s+".join(re.escape(w) for w in anchor.split()), md)
    if match is None:
        pytest.fail(f"{where}: the phrase {anchor!r} is gone, so what follows it cannot be read")
    return match.end()


def codes(cell: str) -> list[str]:
    """Every backticked token in a cell, in order."""
    return [c.strip() for c in _CODE.findall(cell)]


def one_code(cell: str, *, where: str) -> str:
    found = codes(cell)
    if len(found) != 1:
        pytest.fail(f"{where}: expected one backticked token in {cell!r}, found {found}")
    return found[0]


def code_run(md: str, *, where: str, anchor: str | None = None) -> list[str]:
    """The maximal run of backticked tokens separated by `,` or ` · `, starting after `anchor`.

    The shape every inline vocabulary here is written in — `` `browser` · `cli` · `mcp` ``. The run
    ends where the separators do, so trailing prose does not join it.
    """
    start = anchor_end(md, anchor, where=where)
    first = _CODE.search(md, start)
    if first is None:
        pytest.fail(f"{where}: no backticked token after {anchor!r}")
    run = [first.group(1).strip()]
    pos = first.end()
    while (sep := _SEP.match(md, pos)) and (nxt := _CODE.match(md, sep.end())):
        run.append(nxt.group(1).strip())
        pos = nxt.end()
    return run


def brace_list(md: str, *, where: str, anchor: str | None = None) -> list[str]:
    """The comma-separated names inside the first `{…}` after `anchor` — covering both spellings
    used for a record shape: an inline `` `{sha256, …}` `` span and a fenced `{ seq, ts, … }`."""
    match = _BRACE.search(md, anchor_end(md, anchor, where=where))
    if match is None:
        pytest.fail(f"{where}: no `{{…}}` field list after {anchor!r}")
    return [name.strip() for name in match.group(1).split(",") if name.strip()]


def assert_counted(md: str, pattern: str, expected: int, *, where: str) -> None:
    """Every spelled-out count matching `pattern` in `md` must equal `expected`.

    These counts are prose — *"Eighteen names are listed below"*, *"six keys"*, *"all fourteen"* —
    and F8 was a count sentence that outlived its own table. Finding none fails: a deleted count
    stops being checked, which is the same silence. Patterns spell gaps `\\s+`, never a literal
    space — *"six keys"* is split across two lines in `container.md` §8 today.
    """
    words = [m.group(1).lower() for m in re.finditer(pattern, plain(md), re.IGNORECASE)]
    numbers = [NUMBER_WORDS[w] for w in words if w in NUMBER_WORDS]
    if not numbers:
        pytest.fail(f"{where}: no spelled-out count matching {pattern!r} — the sentence is gone")
    assert numbers == [expected] * len(numbers), (
        f"{where}: the document says {words}, the typed shape says {expected}"
    )


# --- typed shapes ------------------------------------------------------------------------------
def protocol_methods(protocol: type) -> frozenset[str]:
    """The methods a Protocol declares in its own body."""
    members = vars(protocol).items()
    return frozenset(n for n, v in members if not n.startswith("_") and callable(v))


def optional_keys(typed_dict: type) -> frozenset[str]:
    """The `NotRequired` keys of a TypedDict.

    Not `__optional_keys__`: `_types.py` carries `from __future__ import annotations`, so its
    annotations reach the TypedDict machinery as strings and every key lands in `__required_keys__`
    whatever it was written as. `get_type_hints` resolves them — what a type checker sees, and so
    what the contract means.
    """
    hints = typing.get_type_hints(typed_dict, include_extras=True)
    return frozenset(k for k, v in hints.items() if typing.get_origin(v) is typing.NotRequired)


# --- container.md §8 · the config object (F6) --------------------------------------------------
def check_container_config(md: str) -> None:
    """§8's key/default table against `CONTAINER_CONFIG_DEFAULTS`, via the F6 wire-key mapping.

    The dotted keys in the left column are canonical (§8), not `ContainerConfig`'s underscored
    field names. `CONTAINER_CONFIG_FIELD_FROM_WIRE_KEY` is the one named crossing between the two;
    this is what makes it a crossing rather than a third spelling.
    """
    where = "container.md §8"
    body = section(md, "8", where=where, nested=False)
    rows = table(body, columns=("key", "default"), where=where)

    mapping = t.CONTAINER_CONFIG_FIELD_FROM_WIRE_KEY
    documented = {one_code(row[0], where=where): row for row in rows}
    assert set(documented) == set(mapping), f"{where}: table keys vs the wire-key mapping"

    # Both count sentences §8 carries, each against the thing it counts.
    assert_counted(body, r"\b(\w+)\s+keys\b", len(mapping), where=where)
    assert_counted(body, r"\b(\w+)\s+rows\b", len(rows), where=where)

    for wire_key, field in mapping.items():
        typed = t.CONTAINER_CONFIG_DEFAULTS[field]
        # The default cell is the value in ticks, sometimes with an unticked gloss after it —
        # `65536` (64 KiB), `300` (≈5 min). The ticked token is the value.
        written = codes(documented[wire_key][1])[0]
        parsed = int(written) if isinstance(typed, int) and written.isdigit() else written
        assert parsed == typed, (
            f"{where}: `{wire_key}` defaults to {written!r} here and {typed!r} in "
            f"CONTAINER_CONFIG_DEFAULTS[{field!r}]"
        )

    # F6's shape was a mapping that lived only in prose, so every surface re-derived it. Keep §8
    # pointing at the constant that replaced it, and naming each key it maps.
    whole = section(md, "8", where=where)
    assert "CONTAINER_CONFIG_FIELD_FROM_WIRE_KEY" in whole, f"{where}: the constant is unnamed"
    for wire_key in mapping:
        assert f"`{wire_key}`" in whole, f"{where}: `{wire_key}` is mapped in code but absent here"


def test_container_config_table_matches_the_typed_defaults() -> None:
    check_container_config(doc("container.md"))


# --- events.md §1–§2 · the taxonomy (F8) -------------------------------------------------------
def test_event_table_matches_the_typed_vocabulary() -> None:
    where = "events.md §1"
    body = section(doc("events.md"), "1", where=where)
    rows = table(body, columns=("event", "status"), where=where)

    names = [one_code(row[0], where=where) for row in rows]
    assert len(names) == len(set(names)), f"{where}: the table lists an event twice: {names}"
    assert set(names) == set(t.EVENTS), f"{where}: the table and `EVENTS` list different events"
    assert_counted(body, r"\b(\w+)\s+names\b", len(t.EVENTS), where=where)


def test_event_status_counts_match_the_prose_sentence() -> None:
    """§1's running / reserved / decided-not-running split, counted three ways: the sentence, the
    table's `status` column, and the events the sentence names by hand. F8 was these disagreeing."""
    where = "events.md §1"
    body = section(doc("events.md"), "1", where=where)
    rows = table(body, columns=("event", "status"), where=where)
    status_of = {one_code(row[0], where=where): plain(row[-1]).strip().lower() for row in rows}
    counts = Counter(status_of.values())

    assert_counted(body, r"\b(\w+)\s+run\b", counts["running"], where=where)

    # The sentence names its own exceptions — "one (`step_up`) is **reserved**". Read the names
    # out of it, so this test carries no event name of its own.
    exceptions = re.findall(r"\b(\w+)\s+\(([\w.]+)\)\s+is\s+(reserved|decided)", plain(body))
    assert exceptions, f"{where}: the sentence no longer names the non-running events"
    for word, event, status in exceptions:
        assert event in t.EVENTS, f"{where}: the prose names `{event}`, which is not in `EVENTS`"
        assert status_of[event].startswith(status), (
            f"{where}: the prose calls `{event}` {status}, the table calls it {status_of[event]!r}"
        )
        assert NUMBER_WORDS[word] == counts[status_of[event]], (
            f"{where}: the prose counts {word} {status_of[event]!r} events, the table has "
            f"{counts[status_of[event]]}"
        )


def test_audit_entry_fields_match_the_entry_block() -> None:
    where = "events.md §2"
    body = section(doc("events.md"), "2", where=where, nested=False)
    documented = brace_list(fence(body, where=where), where=where)
    assert set(documented) == set(t.AuditEntry.__annotations__), f"{where}: vs `AuditEntry`"


# --- context-item.md §1–§5 · the item (F13) ----------------------------------------------------
def test_item_fields_match_context_item_fields() -> None:
    """§1's field table against `CONTEXT_ITEM_FIELDS`.

    Compared as sets: §1 lists `key` before `content` and the tuple lists it after, and neither
    order is meaning — a JSON object's keys are unordered. Drift is a field in one and not the
    other, which is what F13 was.
    """
    where = "context-item.md §1"
    body = section(doc("context-item.md"), "1", where=where)
    rows = table(body, columns=("field", "type", "status"), where=where)
    documented = [one_code(row[0], where=where) for row in rows]
    assert len(documented) == len(set(documented)), f"{where}: a field is listed twice"
    assert set(documented) == set(t.CONTEXT_ITEM_FIELDS), f"{where}: vs `CONTEXT_ITEM_FIELDS`"
    assert set(documented) == set(t.ContextItem.__annotations__), f"{where}: vs `ContextItem`"


def test_kind_vocabulary_matches_kinds() -> None:
    where = "context-item.md §2"
    body = section(doc("context-item.md"), "2", where=where)
    assert set(code_run(body, where=where)) == set(t.KINDS)


def test_provenance_keys_match_the_six_the_document_counts() -> None:
    where = "context-item.md §4"
    body = section(doc("context-item.md"), "4", where=where)
    documented = brace_list(body, where=where)
    assert set(documented) == set(t.Provenance.__annotations__), f"{where}: vs `Provenance`"
    assert_counted(body, r"all\s+(\w+)\s+present", len(documented), where=where)


def test_trust_statuses_and_their_additional_fields() -> None:
    """§5's status vocabulary against `TRUST_STATUSES`, and its table against `Trust`.

    The additional-field column is the whole of what `Trust` carries beyond `status`, and each is
    `NotRequired`: a required `promoted_at` would make an unverified item unrepresentable.
    """
    where = "context-item.md §5"
    body = section(doc("context-item.md"), "5", where=where)

    inline = _CODE.search(body, anchor_end(body, "`status` is", where=where))
    if inline is None:
        pytest.fail(f"{where}: §5 no longer states the status vocabulary inline")
    documented = {s.strip() for s in inline.group(1).split("|")}
    assert documented == set(t.TRUST_STATUSES), f"{where}: the inline list vs `TRUST_STATUSES`"

    rows = table(body, columns=("status", "additional fields"), where=where)
    assert {one_code(r[0], where=where) for r in rows} == documented, f"{where}: table vs prose"
    additional = {name for row in rows for name in codes(row[1])}
    assert additional == optional_keys(t.Trust), f"{where}: vs `Trust`'s NotRequired keys"
    assert set(t.Trust.__annotations__) - additional == {"status"}


# --- authorization-server.md §11.1 and §12 · the AS vocabularies (F25) -------------------------
def test_client_registry_read_fields_match_the_pinned_set() -> None:
    where = "authorization-server.md §11.1"
    body = section(doc("authorization-server.md"), "11.1", where=where)
    documented = frozenset(brace_list(body, where=where, anchor="read one client entry"))
    assert documented == t.AS_CLIENT_REGISTRY_READ_FIELDS, f"{where}: vs the pinned read set"
    assert documented == frozenset(t.ClientRegistration.__annotations__), f"{where}: vs the entry"


def test_client_type_to_consent_kind_mapping() -> None:
    """§11.1's table against `CONSENT_KIND_FROM_CLIENT_TYPE` — F25's mapping, once prose-only.

    Two of the three rows are identities, which is why the mapping needed a name: a reader who
    checks the easy rows renders the third from the literal and emits a copy key that does not
    exist. The copy key is checked against the rendered word, not against a spelling written here.
    """
    where = "authorization-server.md §11.1"
    body = section(doc("authorization-server.md"), "11.1", where=where)
    rows = table(body, columns=("client_type", "rendered kind"), where=where)

    documented, copy_keys = {}, {}
    for row in rows:
        client_type = one_code(row[0], where=where)
        rendered = codes(row[1])
        assert len(rendered) == 2, f"{where}: row {row} is not `kind` · `copy key`"
        documented[client_type] = rendered[0]
        copy_keys[client_type] = rendered[1]

    assert set(documented) == set(t.AS_CLIENT_TYPES), f"{where}: the table's left column drifted"
    assert set(documented.values()) == set(t.CONSENT_KINDS), f"{where}: the rendered words drifted"
    assert documented == t.CONSENT_KIND_FROM_CLIENT_TYPE, f"{where}: vs the pinned mapping"
    namespaces = set()
    for client_type, key in copy_keys.items():
        namespace, _, leaf = key.rpartition(".")
        assert leaf == documented[client_type], (
            f"{where}: `{client_type}` renders as `{documented[client_type]}` but its copy key is "
            f"`{key}` — the key must name the rendered word, not the AS literal"
        )
        namespaces.add(namespace)
    assert len(namespaces) == 1, f"{where}: the copy keys span several namespaces: {namespaces}"


def test_pre_authorization_cause_vocabularies_match_the_as_tuples() -> None:
    """§12's table against the four `AS_*_CAUSES` tuples.

    The row labels are the only names these rows have — `consent.md` §14.8 and §12's own prose
    both cite them as `(a)`…`(f)` — so they are the address, the way a section number is. The
    cause words themselves are read out of the table.
    """
    where = "authorization-server.md §12"
    body = section(doc("authorization-server.md"), "12", where=where, nested=False)
    rows = table(body, columns=("", "the effect", "outcome"), where=where)
    causes = {plain(row[0]).strip(): codes(row[-1]) for row in rows}

    expected = {
        "(a)": t.AS_LOGIN_CAUSES,
        "(b)": t.AS_DEVICE_REDEMPTION_CAUSES,
        "(d)": t.AS_AUTHORIZE_PRETRUST_CAUSES,
        "(f)": t.AS_AUTHORIZE_POSTTRUST_CAUSES,
    }
    assert set(expected) <= set(causes), f"{where}: rows {set(expected) - set(causes)} are gone"
    for label, pinned in expected.items():
        assert set(causes[label]) == set(pinned), (
            f"{where}: row {label}'s causes {causes[label]} and its pinned tuple disagree"
        )
    # (e), a throttle releasing, is the row with no cause vocabulary. A cause appearing there is
    # one nothing pins — the state rows (a), (b), (d) and (f) were just taken out of.
    loose = {k: v for k, v in causes.items() if k not in expected and v}
    assert not loose, f"{where}: {loose} carries causes that no `AS_*` tuple pins"


def test_authorize_pretrust_names_its_own_addition_over_the_design_spec() -> None:
    """Row (d) carries one cause more than `consent.md` §14.8 (d), and says which.

    F25's drift class exactly: a divergence stated in prose and nowhere else. Both halves are read
    out of the document — the six it inherits, the one it adds — and their union must be the tuple.
    """
    where = "authorization-server.md §12, row (d)"
    body = section(doc("authorization-server.md"), "12", where=where, nested=False)

    inherited = code_run(body, where=where, anchor="closes at")
    assert_counted(body, r"closes\s+at\s+(\w+)\s+causes", len(inherited), where=where)

    named = re.search(r"`([\w.]+)`\s+is\s+this\s+Part's\s+own\s+addition", body)
    if named is None:
        pytest.fail(f"{where}: the document no longer names the cause it adds")
    addition = named.group(1)
    assert addition not in inherited, f"{where}: `{addition}` is called an addition but is listed"
    assert set(inherited) | {addition} == set(t.AS_AUTHORIZE_PRETRUST_CAUSES), (
        f"{where}: the inherited causes plus `{addition}` are not the pinned tuple"
    )


def test_authorize_posttrust_excludes_the_cause_it_narrows_away() -> None:
    """Row (f) is two causes, not three: an over-long expiry is clamped (§11.5), never rejected."""
    where = "authorization-server.md §12, row (f)"
    body = section(doc("authorization-server.md"), "12", where=where, nested=False)
    assert_counted(
        body, r"\b(\w+)\s+closed\s+causes\b", len(t.AS_AUTHORIZE_POSTTRUST_CAUSES), where=where
    )
    narrowed = re.search(r"`([\w.]+)`\s+is\s+not\s+a\s+closed\s+cause", body)
    if narrowed is None:
        pytest.fail(f"{where}: the document no longer names the cause it removed")
    assert narrowed.group(1) not in t.AS_AUTHORIZE_POSTTRUST_CAUSES, (
        f"{where}: `{narrowed.group(1)}` is excluded here and pinned by the tuple"
    )


def test_throttle_surface_vocabulary_matches_the_pinned_tuple() -> None:
    where = "authorization-server.md §12.1 rule 5"
    as_doc = doc("authorization-server.md")
    body = section(as_doc, "12.1", where=where)
    pinned = set(t.AS_THROTTLE_SURFACES)
    assert set(code_run(body, where=where, anchor="a closed word,")) == pinned
    # §12 counts the same vocabulary from outside; that count is checked against the tuple too.
    outer = section(as_doc, "12", where=where, nested=False)
    assert_counted(outer, r"\b(\w+)-word\s+surface\s+vocabulary", len(pinned), where=where)


# --- storage.md §1–§4 · the three protocols ----------------------------------------------------
def test_storage_contract_table_matches_storage_contracts() -> None:
    """§1's table against `STORAGE_CONTRACTS`, order included — the tuple is documented as its
    order, so a reorder in one and not the other makes that comment false."""
    where = "storage.md §1"
    body = section(doc("storage.md"), "1", where=where, nested=False)
    rows = table(body, columns=("contract", "method groups"), where=where)
    assert tuple(one_code(row[0], where=where) for row in rows) == t.STORAGE_CONTRACTS


@pytest.mark.parametrize(
    "number, protocol",
    [("2", t.ItemStore), ("3", t.ContainerState), ("4", t.BlobStore)],
    ids=["ItemStore", "ContainerState", "BlobStore"],
)
def test_storage_method_sets_match_the_protocols(number: str, protocol: type) -> None:
    """Each of §2–§4's signature blocks against the Protocol it specifies.

    F3's whole value is *where the line falls*. `tests/_types/test_storage_protocols.py` holds the
    Protocols to the skeleton's method names; this holds them to the document that partitions them.
    """
    where = f"storage.md §{number}"
    body = section(doc("storage.md"), number, where=where, nested=False)
    documented = _SIGNATURE.findall(fence(body, where=where))
    assert len(documented) == len(set(documented)), f"{where}: a method is listed twice"
    assert set(documented) == protocol_methods(protocol), (
        f"{where}: the signature block vs `{protocol.__name__}`"
    )


def test_container_state_method_count_sentence() -> None:
    where = "storage.md §3"
    body = section(doc("storage.md"), "3", where=where, nested=False)
    assert_counted(body, r"\ball\s+(\w+)\b", len(protocol_methods(t.ContainerState)), where=where)


def test_blob_grant_descriptor_agrees_across_both_documents() -> None:
    """`storage.md` §4 and `context-item.md` §3 both state the F5 descriptor, so there are two
    places for it to drift. Both must agree with each other and with `BlobGrant`."""
    for name, number, anchor in [
        ("storage.md", "4", "The descriptor is"),
        ("context-item.md", "3", "other fields are"),
    ]:
        where = f"{name} §{number}"
        body = section(doc(name), number, where=where)
        documented = brace_list(body, where=where, anchor=anchor)
        assert set(documented) == set(t.BlobGrant.__annotations__), f"{where}: vs `BlobGrant`"


# --- the parser is not vacuous -----------------------------------------------------------------
# Everything above passes if the parser quietly finds nothing. These four break a document on
# purpose and require the helpers to fail on it.


def test_meta_a_missing_section_number_fails() -> None:
    with pytest.raises(pytest.fail.Exception):
        section(doc("events.md"), "99", where="meta")


def test_meta_a_renumbered_heading_fails() -> None:
    """Renaming a heading must not turn a check off — §8's own check must stop passing, loudly."""
    md = doc("container.md")
    heading = next(line for line in md.splitlines() if line.startswith("## 8 ·"))
    with pytest.raises(pytest.fail.Exception):
        check_container_config(md.replace(heading, heading.replace("## 8 ·", "## 8bis ·"), 1))


def test_meta_a_renamed_column_fails() -> None:
    where = "meta"
    body = section(doc("container.md"), "8", where=where, nested=False)
    with pytest.raises(pytest.fail.Exception):
        table(body, columns=("key", "defaults-renamed"), where=where)


def test_meta_a_changed_default_fails() -> None:
    """#103's acceptance criterion: a deliberately broken row fails the check. Row and mutation
    both come from the document — the first integer default in §8, bumped by one in its own table
    line — so this stays honest if §8's rows change."""
    md = doc("container.md")
    where = "meta"
    rows = table(section(md, "8", where=where, nested=False),
                 columns=("key", "default"), where=where)
    row = next(r for r in rows if codes(r[1])[0].isdigit())
    key, value = one_code(row[0], where=where), codes(row[1])[0]
    line = next(x for x in md.splitlines() if x.startswith("|") and f"`{key}`" in x)
    broken = md.replace(line, line.replace(f"`{value}`", f"`{int(value) + 1}`", 1), 1)
    assert broken != md
    with pytest.raises(AssertionError):
        check_container_config(broken)
