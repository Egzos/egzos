#!/usr/bin/env python3
# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Stands in for a person at a browser, for the demo and tests only: given a /tap/<token> URL it
opens the page, presses *Sign and approve*, then *Confirm signature* — the same two deliberate
presses the page asks of a human, over the same HTTP.
Usage: BROWSER="python tests/human_tap.py %s" (or `--deny URL`, or `--once URL` to approve
without a window).
It holds no credential and does nothing a person's browser could not — which is exactly why it
lives with the tests: it is the named residual (anything running as the user can press), made
explicit, not a feature of the product."""

from __future__ import annotations

import sys
import urllib.request
from urllib.parse import urlparse


def press(url: str, step: str) -> str:
    origin = "{0.scheme}://{0.netloc}".format(urlparse(url))
    req = urllib.request.Request(url, data=f"step={step}".encode(), headers={"Origin": origin})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode()


def main(argv: list[str]) -> int:
    deny, once = "--deny" in argv, "--once" in argv
    url = [a for a in argv if not a.startswith("--")][0]
    urllib.request.urlopen(url, timeout=10).read()
    if deny:
        press(url, "deny")
        return 0
    press(url, "arm_once" if once else "arm")
    press(url, "confirm")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
