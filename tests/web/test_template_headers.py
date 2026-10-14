# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Drift report F35 (#10, #246): every template under `src/egzos/web/templates/` carries the
licence header as a Jinja comment, and the comment never reaches a rendered page."""

from __future__ import annotations

from importlib import resources

import pytest
from fastapi.testclient import TestClient

from egzos.container import OWNER, Container
from egzos.web.app import Lifeboat, create_app

ORIGIN = "http://testserver"
COPYRIGHT = "Copyright 2026 Ali Sasanian"
SPDX = "SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0"


def _template_paths():
    directory = resources.files("egzos.web").joinpath("templates")
    return sorted((p for p in directory.iterdir() if p.name.endswith(".html")), key=str)


def test_templates_directory_is_not_accidentally_empty():
    assert len(_template_paths()) == 9  # the nine templates F35 counted


@pytest.mark.parametrize("path", _template_paths(), ids=lambda p: p.name)
def test_template_carries_both_header_lines(path):
    text = path.read_text(encoding="utf-8")
    assert COPYRIGHT in text, f"{path.name} is missing the copyright line"
    assert SPDX in text, f"{path.name} is missing the SPDX line"


@pytest.fixture
def lb(tmp_path, monkeypatch):
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    monkeypatch.setenv("EGZOS_STEP_UP_WINDOW_SECONDS", "0")
    c = Container(tmp_path / "home")
    token = c.init()
    c.store.add(body="x", kind="preference", key="k", tags=[], token=token, actor=OWNER,
                principal="interactive")
    boat = Lifeboat(c, key="k" * 32, host="testserver")
    client = TestClient(create_app(boat, ORIGIN), base_url=ORIGIN)
    assert client.get(f"/?k={boat.key}", follow_redirects=False).status_code == 303
    return boat, client


@pytest.mark.parametrize("path", ["/", "/pending"])
def test_rendered_page_carries_no_trace_of_the_header(lb, path):
    _boat, client = lb
    r = client.get(path)
    assert r.status_code == 200
    assert COPYRIGHT not in r.text
    assert SPDX not in r.text
    # The comment's trailing newline is trimmed too: the header adds no leading blank line.
    assert r.text.startswith("<!doctype html>")
