#!/usr/bin/env bash
# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
# Post or update exactly ONE review comment on a PR, identified by its first line ("## <agent> review")
# AND by author. Deterministic replacement for the action's tag-mode sticky comment, which never
# exists in automation mode.
# Usage: bash .github/scripts/post_review_comment.sh <pr-number> <body-file>
# Requires: GH_TOKEN with pull-requests: write (the default Actions token is enough); GITHUB_REPOSITORY set.
set -euo pipefail
PR="${1:?pr number}"; BODY_FILE="${2:?body file}"; REPO="${GITHUB_REPOSITORY:?}"
MARKER="$(head -n1 "$BODY_FILE")"
case "$MARKER" in
  "## "*" review") ;;
  *) echo "::error::review body must start with '## <agent> review' (got: ${MARKER:0:60})"; exit 2 ;;
esac

# Author filter is load-bearing, not cosmetic: on a public repository any account can post a comment
# starting with this marker. Without it the reviewer would PATCH that comment, putting its verdict
# under a foreign identity that its owner can then edit. Match only our own runner identity.
AUTHOR="github-actions[bot]"

# No `|| true`: a failed lookup must fail the step, not fall through to POST and stack a duplicate.
COMMENTS="$(gh api --paginate "repos/$REPO/issues/$PR/comments")"
EXISTING="$(printf '%s' "$COMMENTS" \
  | jq -r --arg m "$MARKER" --arg a "$AUTHOR" \
      'if type=="array" then .[] else .[]? end
       | select(.user.login == $a)
       | select(.body | startswith($m))
       | .id' \
  | head -n1)"

if [[ -n "$EXISTING" ]]; then
  gh api -X PATCH "repos/$REPO/issues/comments/$EXISTING" -F body=@"$BODY_FILE" >/dev/null
  echo "updated review comment $EXISTING on PR #$PR"
else
  gh api -X POST "repos/$REPO/issues/$PR/comments" -F body=@"$BODY_FILE" >/dev/null
  echo "created review comment on PR #$PR"
fi
