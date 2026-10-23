# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §2 item 7's throttle, past one window: its secret, catching up, and forgetting."""

from __future__ import annotations

import stat
import threading

from egzos.api.throttle import KEEP_WINDOWS, KEY_BYTES, WINDOW_SECONDS, Throttle, throttle_key
from egzos.container import Container


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


def _events(c, name):
    return [e for e in c.ledger.tail(1000) if e["event"] == name]


def test_the_key_is_created_once_whole_and_private(tmp_path):
    keys: list[bytes] = []
    gate = threading.Barrier(8)

    def read():
        gate.wait()
        keys.append(throttle_key(tmp_path))

    threads = [threading.Thread(target=read) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(keys)) == 1 and len(keys[0]) == KEY_BYTES
    assert stat.S_IMODE((tmp_path / "throttle.key").stat().st_mode) == 0o600
    assert sorted(p.name for p in tmp_path.iterdir()) == ["throttle.key"]


def test_a_short_key_left_by_a_crash_is_passed_over_never_rewritten(tmp_path):
    (tmp_path / "throttle.key").write_bytes(b"short")
    keys: list[bytes] = []
    gate = threading.Barrier(8)

    def read():
        gate.wait()
        keys.append(throttle_key(tmp_path))

    threads = [threading.Thread(target=read) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(keys)) == 1 and len(keys[0]) == KEY_BYTES  # one key, whoever repaired
    assert (tmp_path / "throttle.key").read_bytes() == b"short"
    assert (tmp_path / "throttle.key.1").read_bytes() == keys[0]


def test_a_window_closed_while_the_door_was_down_still_releases(tmp_path):
    c = Container(tmp_path)
    c.init()
    clock = Clock()
    throttle = Throttle(c.backend, c.ledger, b"k" * 32, clock=clock)
    throttle.count("1.2.3.4", refused=False)
    clock.now += WINDOW_SECONDS * (KEEP_WINDOWS + 30)  # a long time down
    throttle.close()
    assert len(_events(c, "rest.tally")) == 1
    # and, being older than the keep, its counters are gone
    assert c.backend.throttle_windows("rest") == []


def test_closed_windows_are_forgotten_after_the_keep(tmp_path):
    c = Container(tmp_path)
    c.init()
    clock = Clock()
    throttle = Throttle(c.backend, c.ledger, b"k" * 32, clock=clock)
    throttle.count("1.2.3.4", refused=False)
    first = c.backend.throttle_windows("rest")
    clock.now += WINDOW_SECONDS
    throttle.close()
    assert c.backend.throttle_windows("rest") == first  # closed, still kept
    clock.now += WINDOW_SECONDS * KEEP_WINDOWS
    throttle.close()
    assert c.backend.throttle_windows("rest") == []
    assert len(_events(c, "rest.tally")) == 1  # closed once, never again
