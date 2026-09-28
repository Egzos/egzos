#!/usr/bin/env bash
# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
# The a6-adversary nightly sweep's only route to the repository-advisory API. It replaces a raw
# `gh api:*` grant, which handed the forge token's whole reach to the one session built to read
# attacker-shaped text (drift F17). Three verbs, one endpoint family, this repository only.
#
#   file_advisory.sh list                          existing advisories: GHSA id, state, summary
#   file_advisory.sh create <json-file>            file one; prints its GHSA id
#   file_advisory.sh update <GHSA-id> <json-file>  append to one already filed; prints its GHSA id
#
# update is append-only. The advisory body is the only copy of an unfixed reproduction, and the API's
# PATCH replaces each field it is given, so the script reads the filed advisory itself: the new
# file's `description` (required) is appended under a dated heading, its `vulnerabilities` are
# added to the filed ones, and `severity` is replaced only if given. Nothing else is sent. Every
# vulnerability, filed or new, is cut down to the fields PATCH accepts before the union: a GET
# returns the read shape, and echoing it back verbatim is what a PATCH may refuse.
#
# Requires GH_TOKEN (the forge token) and GITHUB_REPOSITORY. Prints ids and summaries only: the
# body carrying a reproduction goes to the API from the file and never to stdout.
set -euo pipefail
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is not set}"

usage() {
  echo "usage: file_advisory.sh list | create <json-file> | update <GHSA-id> <json-file>" >&2
  exit 2
}

body_file() {
  [[ -f "${1:-}" && -s "$1" ]] || { echo "file_advisory.sh: no such non-empty file: ${1:-}" >&2; exit 2; }
  jq -e 'type == "object"' "$1" >/dev/null || { echo "file_advisory.sh: body is not a JSON object" >&2; exit 2; }
}

case "${1:-}" in
  list)
    [[ $# -eq 1 ]] || usage
    gh api --paginate "repos/${REPO}/security-advisories?per_page=100" \
      --jq '.[] | [.ghsa_id, .state, .summary] | @tsv'
    ;;
  create)
    [[ $# -eq 2 ]] || usage
    body_file "$2"
    gh api -X POST "repos/${REPO}/security-advisories" --input "$2" --jq '.ghsa_id'
    ;;
  update)
    [[ $# -eq 3 ]] || usage
    [[ "$2" =~ ^GHSA(-[23456789cfghjmpqrvwx]{4}){3}$ ]] || { echo "file_advisory.sh: not a GHSA id: $2" >&2; exit 2; }
    body_file "$3"
    jq -e '(.description | type) == "string" and (.description | length) > 0' "$3" >/dev/null \
      || { echo "file_advisory.sh: update needs a non-empty description to append" >&2; exit 2; }
    CURRENT="$(gh api "repos/${REPO}/security-advisories/$2")"
    jq -n --argjson cur "$CURRENT" --slurpfile new "$3" --arg day "$(date -u +%F)" '
        def writable: {package: {ecosystem: .package.ecosystem, name: .package.name}}
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
