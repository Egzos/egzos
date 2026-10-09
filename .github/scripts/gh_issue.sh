#!/usr/bin/env bash
# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
# The only route to issue writes for the model sessions that hold no interpreter: a6's nightly sweep
# and a1r's nightly drift report. It replaces raw `gh issue create|edit|comment:*` grants. A prefix
# grant approves any flag, and `--body-file` (`-F`) makes gh read and post whatever path it names,
# /proc/self/environ included, which Read(//proc/**) does not cover because the read is gh's.
#
#   gh_issue.sh create <title> <body-file> [label ...]   open one issue; prints its number
#   gh_issue.sh comment <number> <body-file>              comment on one issue
#   gh_issue.sh edit <number> <body-file>                 replace one issue's body
#
# A body file must sit in AGENT_OUT_DIR (default /tmp/agent-out), resolved, symlinks included. The
# sessions write there with a Write grant scoped to that one directory, which never reaches this
# script. A body carrying a credential this process can see is refused, never posted. Requires
# GH_TOKEN and GITHUB_REPOSITORY. Prints numbers only.
set -euo pipefail
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is not set}"

usage() {
  echo "usage: gh_issue.sh create <title> <body-file> [label ...] | comment <number> <body-file> | edit <number> <body-file>" >&2
  exit 2
}

# Sets BODY to the resolved body file, refusing anything outside the directory or carrying a credential.
body() {
  local dir
  dir="$(realpath -m "${AGENT_OUT_DIR:-/tmp/agent-out}")"
  BODY="$(realpath -e -- "${1:-}" 2>/dev/null)" || BODY=""
  [[ -n "$BODY" && "$BODY" == "$dir"/* && -f "$BODY" && -s "$BODY" ]] \
    || { echo "gh_issue.sh: a body file must be a non-empty file in $dir" >&2; exit 2; }
  local text cred
  text="$(cat -- "$BODY")"
  for cred in "${GH_TOKEN:-}" "${GITHUB_TOKEN:-}" "${ANTHROPIC_API_KEY:-}" "${CLAUDE_CODE_OAUTH_TOKEN:-}"; do
    if [[ -n "$cred" && "$text" == *"$cred"* ]]; then
      echo "gh_issue.sh: the body carries a credential; nothing posted" >&2
      exit 2
    fi
  done
}

number() {
  [[ "${1:-}" =~ ^[0-9]+$ ]] || { echo "gh_issue.sh: not an issue number: ${1:-}" >&2; exit 2; }
}

case "${1:-}" in
  create)
    [[ $# -ge 3 ]] || usage
    title="$2"
    [[ -n "$title" && "$title" != *$'\n'* && ${#title} -le 256 ]] \
      || { echo "gh_issue.sh: a title is one non-empty line of at most 256 characters" >&2; exit 2; }
    body "$3"
    labels=()
    for label in "${@:4}"; do
      [[ "$label" =~ ^[a-z0-9][a-z0-9:_-]{0,49}$ ]] || { echo "gh_issue.sh: bad label: $label" >&2; exit 2; }
      labels+=(-f "labels[]=$label")
    done
    gh api -X POST "repos/${REPO}/issues" -f "title=$title" -F "body=@$BODY" "${labels[@]}" --jq '.number'
    ;;
  comment)
    [[ $# -eq 3 ]] || usage
    number "$2"
    body "$3"
    gh api -X POST "repos/${REPO}/issues/$2/comments" -F "body=@$BODY" --jq '.id' > /dev/null
    echo "$2"
    ;;
  edit)
    [[ $# -eq 3 ]] || usage
    number "$2"
    body "$3"
    gh api -X PATCH "repos/${REPO}/issues/$2" -F "body=@$BODY" --jq '.number'
    ;;
  *)
    usage
    ;;
esac
