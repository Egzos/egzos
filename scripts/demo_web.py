# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""Demo only (never merged): seed a throwaway container and serve the lifeboat for a recording.

    python scripts/demo_web.py            # seeds /tmp/egzos-demo, serves http://127.0.0.1:8765
    python scripts/demo_web.py PATH PORT

It prints the one URL to open (it carries this run's session key). What it seeds:
- org:acme with projects atlas and research; a verified preference, a rule, a memory, a file;
- an agent (client token `claude-code`) whose writes land UNVERIFIED with its name on them;
- one parked proposal: the agent moving its vendor shortlist into `research`, where a partner
  (`partner-review`) can see it. The audience widens, so the gate parks it for the human.
Presence windows are 5 minutes, so the second approval within them shows the window line.
"""

import os
import secrets
import shutil
import sys
from pathlib import Path

os.environ.setdefault("EGZOS_STEP_UP_WINDOW_SECONDS", "300")

import uvicorn  # noqa: E402

from egzos.container import OWNER, Container  # noqa: E402
from egzos.web.app import Lifeboat, create_app  # noqa: E402

home = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/egzos-demo")
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
shutil.rmtree(home, ignore_errors=True)
c = Container(home / "home")
c.init()
t = c.auth.interactive_token()
me = {"token": t, "actor": OWNER, "principal": "interactive"}

root = c.nodes.user_root()
acme = c.nodes.create("org", "acme", root, **me)
atlas = c.nodes.create("project", "atlas", acme, **me)
research = c.nodes.create("project", "research", acme, **me)

style = c.store.add(body="Prefer imperative commit messages; one subject line under 72 characters.",
                    kind="preference", key="commit.style", tags=["style"], **me)
c.trust.promote(style, token=t, actor=OWNER)
c.store.add(body="Never push to main. Every change goes through a reviewed PR.", kind="rule",
            scope=atlas, tags=["process"], **me)
c.store.add(body="Atlas launch vendors: Acme Logistics and Globex.\nRenewals are due in Q4.",
            kind="memory", scope=atlas, tags=["vendors"], **me)
plan = home / "q4-plan.md"
plan.write_text("# Q4 plan\n\n- Ship the lifeboat\n- Freeze the contracts\n- Demo day\n")
c.store.add(file=plan, scope=atlas, tags=["planning"], **me)
c.store.add(body="Call notes: the partner review needs the vendor shortlist by Friday.", **me)

agent = c.auth.mint(principal="client", owner=OWNER, client="claude-code", role="operator",
                    scopes=[acme.id], actor=OWNER, by_principal="interactive")
bot = {"token": agent, "actor": "claude-code", "principal": "client"}
c.store.add(body="Tests run with `pytest -q`; lint with `ruff check .` before every push.",
            kind="memory", scope=research, tags=["dev"], **bot)
shortlist = c.store.add(body="Vendor shortlist (draft): Acme Logistics, Globex, Initech.",
                        kind="memory", scope=atlas, tags=["vendors"], **bot)
c.store.add(body="The user prefers concise PR descriptions with a Risk section.",
            kind="preference", scope=research, **bot)

c.auth.mint(principal="client", owner=OWNER, client="partner-review", role="reader",
            scopes=[research.id], actor=OWNER, by_principal="interactive")
c.trust.move(c.backend.get(shortlist.id), research, token=agent, actor="claude-code")

key = secrets.token_urlsafe(24)
origin = f"http://127.0.0.1:{port}"
print(f"egzos demo lifeboat — open: {origin}/?k={key}", flush=True)
print(f"container home: {home / 'home'}  (EGZOS_HOME for CLI commands against it)", flush=True)
uvicorn.run(create_app(Lifeboat(c, key=key, host=f"127.0.0.1:{port}"), origin),
            host="127.0.0.1", port=port, log_level="warning")
