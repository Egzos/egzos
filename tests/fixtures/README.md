# tests/fixtures

Shared test fixtures — owned by haiku-mechanic.

This directory holds static data files used across the test suite (example context items,
serialized store snapshots, sample `.xmb` archives). Fixtures are excluded from the PR
size cap.

Individual module fixture files live alongside the module's tests:
`tests/<module>/fixtures/`.

haiku-mechanic adds fixtures via its queue; no agent places files here without a PR.
