# adversarial/

Attack-shaped tests — owned exclusively by a6-adversary.

## What lives here

Tests that attempt to break egzos from the outside: injected `--yes` / echo-y payloads, TOCTOU races
against manifest binding, enumeration via error shapes, proposal-target probing, staging prefix abuse,
token-sweep gaps, OAuth surface attacks (PKCE downgrade, redirect-URI allowlist bypass, consent
phishing), Herald pipeline poisoning (poisoned PR body flowing into a misleading digest), and
catalogue-content injection.

The standing target list grows. a6-adversary maintains it from the decisions log and its own sweep runs.

## The disclosure split

This repository is public. The split between security and non-security findings exists because an xfail
with a repro in a public repository is a zero-day disclosure.

- **Security findings** — do not live here until fixed. The reproduction goes into a private GitHub
  Security Advisory. The regression test enters `adversarial/` only in the fix PR, flipping from absent
  to passing.
- **Non-security findings** (behavior gaps, contract mismatches) — use `@pytest.mark.xfail_finding`
  here, linked to a public issue. The fix PR flips the marker.

## The xfail pattern

Mark a known non-security finding like this:

```python
import pytest

@pytest.mark.xfail_finding
@pytest.mark.xfail(reason="known finding — see issue #<N>", strict=True)
def test_enumeration_through_404_shape():
    # Demonstrates that a missing item returns a distinguishable error shape.
    # Fix PR will flip strict=True xfail to a passing test.
    ...
```

`strict=True` means the test fails the suite if the behavior is accidentally fixed without removing the
marker — a guard against silent regressions.

## Ownership

a6-adversary owns `adversarial/**` exclusively. No other agent writes here. The Chief may edit directly.
Path ownership is enforced by the `ownership` check on every PR.
