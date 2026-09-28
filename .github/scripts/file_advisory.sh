#!/usr/bin/env bash
# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
# The a6-adversary nightly sweep's only route to the repository-advisory API. It replaces a raw
# `gh api:*` grant, which handed the forge token's whole reach to the one session built to read
# attacker-shaped text (drift F17). Three verbs, one endpoint family, this repository only.
#
#   file_advisory.sh list                                  GHSA id, state, summary per advisory
#   file_advisory.sh create <json-file | ->                file one; prints its GHSA id
#   file_advisory.sh update <GHSA-id> <json-file | ->      append to one already filed; prints its id
#
# `-` reads the body from standard input. The sweep passes it that way because its session holds no
# write tool: a session that could write files and also run a script it could have rewritten would
# hold an interpreter with the forge token behind it (Egzos/egzos#71 review, round 3).
#
# update is append-only. The advisory body is the only copy of an unfixed reproduction, and the API's
# PATCH replaces each field it is given, so the script reads the filed advisory itself: the new
# file's `description` (required) is appended under a dated heading, its `vulnerabilities` are
# added to the filed ones, and `severity` is replaced only if given. Nothing else is sent. Every
# vulnerability, filed or new, is cut down to the fields PATCH accepts before the union: a GET
# returns the read shape, and echoing it back verbatim is what a PATCH may refuse.
#
# Requires GH_TOKEN (the forge token) and GITHUB_REPOSITORY. Prints ids and summaries only: the
# body carrying a reproduction goes to the API from the file and never to stdout. `list`'s summaries
# reach the model, not the job log: no workflow sets the action's show_full_output (pinned by
# tests/governance/test_workflows.py).
set -euo pipefail
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is not set}"

usage() {
  echo "usage: file_advisory.sh list | create <json-file|-> | update <GHSA-id> <json-file|->" >&2
  exit 2
}

# Sets BODY to the file to read: the named file, or standard input spooled to a private temporary
# file that is removed on exit. Runs in this shell, never a subshell, so the trap outlives it.
spool() {
  if [[ "${1:-}" == "-" ]]; then
    BODY="$(mktemp)"
    trap 'rm -f "$BODY"' EXIT
    cat > "$BODY"
  else
    BODY="${1:-}"
  fi
  [[ -f "$BODY" && -s "$BODY" ]] || { echo "file_advisory.sh: no non-empty body: ${1:-}" >&2; exit 2; }
  jq -e 'type == "object"' "$BODY" >/dev/null || { echo "file_advisory.sh: body is not a JSON object" >&2; exit 2; }
}

case "${1:-}" in
  list)
    [[ $# -eq 1 ]] || usage
    gh api --paginate "repos/${REPO}/security-advisories?per_page=100" \
      --jq '.[] | [.ghsa_id, .state, .summary] | @tsv'
    ;;
  create)
    [[ $# -eq 2 ]] || usage
    spool "$2"
    gh api -X POST "repos/${REPO}/security-advisories" --input "$BODY" --jq '.ghsa_id'
    ;;
  update)
    [[ $# -eq 3 ]] || usage
    [[ "$2" =~ ^GHSA(-[23456789cfghjmpqrvwx]{4}){3}$ ]] || { echo "file_advisory.sh: not a GHSA id: $2" >&2; exit 2; }
    spool "$3"
    jq -e '(.description | type) == "string" and (.description | length) > 0' "$BODY" >/dev/null \
      || { echo "file_advisory.sh: update needs a non-empty description to append" >&2; exit 2; }
    CURRENT="$(gh api "repos/${REPO}/security-advisories/$2")"
    jq -n --argjson cur "$CURRENT" --slurpfile new "$BODY" --arg day "$(date -u +%F)" '
        def writable: (if (.package.ecosystem and .package.name)
                       then {package: {ecosystem: .package.ecosystem, name: .package.name}}
                       else {} end)
          + ({vulnerable_version_range, patched_versions, vulnerable_functions}
             | with_entries(select(.value != null)));
        $new[0] as $n
        | {description: (($cur.description // "") + "\n\n### Update " + $day + "\n\n" + $n.description)}
        + (if $n.severity then {severity: $n.severity} else {} end)
        + (if $n.vulnerabilities
             then {vulnerabilities: ([($cur.vulnerabilities // [])[], $n.vulnerabilities[]]
                                     | map(writable) | unique)}
             else {} end)' \
      | gh api -X PATCH "repos/${REPO}/security-advisories/$2" --input - --jq '.ghsa_id'
    ;;
  *)
    usage
    ;;
esac
