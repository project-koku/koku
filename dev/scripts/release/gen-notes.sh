#!/usr/bin/env bash
# gen-notes.sh — Prepare koku GitHub Release
#
# Usage:
#   gen-notes.sh <from-tag> <to-sha>
#
# Env:
#   KOKU_DIR — koku checkout (default: repo root of this script)

set -euo pipefail

FROM_TAG="${1:?Usage: gen-notes.sh <from-tag> <to-sha>}"
TO_SHA="${2:?Usage: gen-notes.sh <from-tag> <to-sha>}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

cd "$KOKU_DIR"
git fetch origin --tags -q 2>/dev/null || true

TODAY=$(date '+%Y.%m.%d')
EXISTING=$(gh release list --repo project-koku/koku --limit 10 --json tagName \
  -q '.[].tagName' 2>/dev/null | grep "^r\.${TODAY}\." || true)
if [[ -z "$EXISTING" ]]; then
  NEXT_TAG="r.${TODAY}.0"
else
  LAST_PATCH=$(echo "$EXISTING" | sort | tail -1 | sed "s/r\.${TODAY}\.//")
  NEXT_TAG="r.${TODAY}.$((LAST_PATCH + 1))"
fi

COMMIT_COUNT=$(git log "${FROM_TAG}..${TO_SHA}" --no-merges --oneline 2>/dev/null | wc -l | tr -d ' ')
COMMIT_SUBJECTS=$(git log "${FROM_TAG}..${TO_SHA}" --no-merges \
  --pretty=format:"  • %s" 2>/dev/null)
COST_TICKETS=$(git log "${FROM_TAG}..${TO_SHA}" --no-merges --pretty=format:"%s" 2>/dev/null \
  | grep -oE 'COST-[0-9]+' | sort -u | paste -sd ', ' - || true)

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║          RELEASE NOTES PREPARATION              ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "Tag          : ${NEXT_TAG}"
echo "Target SHA   : ${TO_SHA}"
echo "From         : ${FROM_TAG}"
echo "Commits      : ${COMMIT_COUNT}"
echo "Jira tickets : ${COST_TICKETS:-none}"
echo ""
echo "── Commits (for Summary writing) ────────────────"
echo "$COMMIT_SUBJECTS"
echo ""
echo "──────────────────────────────────────────────────"
echo "📝 AGENT: Based on the commits above, write a"
echo "   concise Summary section (1-5 bullet points or"
echo "   a short paragraph). Use the style of past releases:"
echo ""
echo "   Style A (short): 'Bug fixes and improvements'"
echo "   Style B (medium): 'This release adds X, fixes Y, and updates Z.'"
echo "   Style C (detailed): bullet list of key changes"
echo ""
echo "   Pattern from recent releases:"
echo "   - 1-2 commits → one-liner summary"
echo "   - 3-10 commits → short paragraph or 3-5 bullets"
echo "   - 10+ commits → detailed bullets with feature grouping"
echo ""
echo "── COMMAND TO RUN after Summary is approved ─────"
echo ""
echo "  gh release create ${NEXT_TAG} \\"
echo "    --repo project-koku/koku \\"
echo "    --title \"${NEXT_TAG}\" \\"
echo "    --target ${TO_SHA} \\"
echo "    --prerelease \\"
echo "    --generate-notes \\"
echo "    --notes-start-tag ${FROM_TAG} \\"
echo "    --notes \"\$(cat <<'EONOTES'"
echo "### Summary:"
echo ""
echo "<AGENT_WRITES_SUMMARY_HERE>"
echo ""
echo "EONOTES"
echo ")\""
echo ""
echo "── After release is created ──────────────────────"
echo "   1. Open: https://github.com/project-koku/koku/releases/tag/${NEXT_TAG}"
echo "   2. Click Edit → review the auto-generated 'What's Changed'"
echo "   3. Uncheck 'Set as a pre-release'"
echo "   4. Check 'Set as the latest release'"
echo "   5. Save"
echo ""
echo "Also see: docs/generating-release-notes.md"
