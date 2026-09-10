#!/usr/bin/env bash
# Post or update exactly ONE review comment on a PR, identified by its first line ("## <agent> review").
# Deterministic replacement for the action's tag-mode sticky comment, which never exists in automation mode.
# Usage: bash .github/scripts/post_review_comment.sh <pr-number> <body-file>
# Requires: GH_TOKEN with pull-requests: write (the default Actions token is enough); GITHUB_REPOSITORY set.
set -euo pipefail
PR="${1:?pr number}"; BODY_FILE="${2:?body file}"; REPO="${GITHUB_REPOSITORY:?}"
MARKER="$(head -n1 "$BODY_FILE")"
case "$MARKER" in
  "## "*" review") ;;
  *) echo "::error::review body must start with '## <agent> review' (got: ${MARKER:0:60})"; exit 2 ;;
esac
EXISTING="$(gh api --paginate "repos/$REPO/issues/$PR/comments" \
  --jq ".[] | select(.body | startswith(\"$MARKER\")) | .id" | head -n1 || true)"
if [[ -n "$EXISTING" ]]; then
  gh api -X PATCH "repos/$REPO/issues/comments/$EXISTING" -F body=@"$BODY_FILE" >/dev/null
  echo "updated review comment $EXISTING on PR #$PR"
else
  gh api -X POST "repos/$REPO/issues/$PR/comments" -F body=@"$BODY_FILE" >/dev/null
  echo "created review comment on PR #$PR"
fi
