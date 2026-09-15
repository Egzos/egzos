#!/usr/bin/env bash
# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
#
# The walking skeleton, end to end, in a throwaway container: add → inbox → resolve → serve --mcp → audit.
# The Chief is the acceptance test (build plan 2.5, pulled forward). Run from the repo root:
#
#   scripts/demo.sh            # uses .venv/bin/python if present, else python3 (3.11+)
#
set -euo pipefail
PY="${PY:-$( [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3 )}"
export PYTHONPATH="${PYTHONPATH:-src}"
export EGZOS_HOME="$(mktemp -d)"
E="$PY -m egzos.cli"
say() { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }
run() { printf '\033[2m$ egzos %s\033[0m\n' "$*"; $E "$@"; }

say "1 · a container is born: two roots, an inbox, the owner's interactive token"
run init
run whoami

say "2 · capture — three adds, no scope: each opens an auto-titled thread in the inbox, all unverified"
run add "Always write commit messages in the imperative." --kind preference --key commit.style
printf 'Meeting 2026-09-14\nDecided: Opus 5 for the frontier tier.\n' | run add -
printf 'never paste secrets into chat\n' > "$EGZOS_HOME/policy.txt"
run add "Never paste secrets into chat." --kind rule --key secrets.policy
run ls --inbox

say "3 · structure is free; connecting is deliberate"
run mk project health
run mk org acme
run find commit
run mv %1 project:health          # solo container: zero audience delta → silent gate pass

say "4 · an agent that can see the org — now moving there is a publish"
run token create --client ops-agent --role operator --scope org:acme
run find commit
run mv %1 org:acme                # the gate: resolved audience + inheritance, parked in pending
run trust pending
PID=$($E --json trust pending | $PY -c "import json,sys; print(json.load(sys.stdin)['proposals'][0]['id'])")
run trust approve "$PID"          # human yes, manifest-bound

say "5 · serving policy: unverified is withheld at the org; promotion serves it; rules everywhere"
run fetch org:acme --no-global
run find commit
run trust approve %1
run fetch org:acme --no-global
RT=$($E --json find secrets | $PY -c "import json,sys; print(json.load(sys.stdin)[0]['scope'])")
run fetch "$RT" --no-global --kind rule   # rule withheld until promoted — even in its own thread
run find secrets; run trust approve %1
run fetch "$RT" --no-global --kind rule

say "6 · the door: Claude Code (stood in by scripts/mcp_client_probe.py) as the client principal"
CT=$($E --json token ls | $PY -c "import json,sys; print([t['id'] for t in json.load(sys.stdin) if t['client']=='ops-agent'][0])")
printf '\033[2m$ EGZOS_TOKEN=<ops-agent> python scripts/mcp_client_probe.py\033[0m\n'
EGZOS_TOKEN="$CT" $PY scripts/mcp_client_probe.py
printf '\033[2m$ egzos serve --mcp --token <interactive>\033[0m\n'
$E serve --mcp --token "$($PY -c "import json;print(json.load(open('$EGZOS_HOME/keychain.json'))['token'])")" || true

say "7 · the record: every read, every silent pass, every yes — and a chain that verifies"
run audit tail -n 14
run audit verify

say "done — container at $EGZOS_HOME (delete it; the skeleton is throwaway by decision)"
