#!/usr/bin/env bash
# analyze.sh — Koku release readiness report
# Usage:
#   analyze.sh                       — full release readiness report
#   analyze.sh migrations <sha>      — migration check between prod and <sha>
#
# Env:
#   KOKU_DIR              — koku checkout (default: repo root of this script)
#   APP_INTERFACE_DIR     — app-interface clone (default: ~/development/app-interface)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

cmd="${1:-report}"
shift || true

require_app_interface

get_prod_ref() {
  python3 - <<PYEOF
with open("${DEPLOY_FILE}") as f:
    content = f.read()
in_prod = False
for line in content.splitlines():
    if 'hccm-prod.yml' in line:
        in_prod = True
        continue
    if in_prod and line.strip().startswith('ref:') and '\$ref' not in line:
        print(line.split('ref:')[1].strip())
        break
PYEOF
}

check_pg_migrations() {
  local from_sha="$1" to_sha="$2"
  git -C "$KOKU_DIR" diff --name-only "${from_sha}..${to_sha}" 2>/dev/null \
    | grep -E "koku/.+/migrations/[0-9]+.*\.py" || true
}

check_trino_migrations() {
  local from_sha="$1" to_sha="$2"
  git -C "$KOKU_DIR" diff --name-only "${from_sha}..${to_sha}" 2>/dev/null \
    | grep -iE "trino.*migrat|migrat.*trino|koku/trino/" || true
}

if [[ "$cmd" == "report" ]]; then
  cd "$KOKU_DIR"
  git fetch origin --tags -q 2>/dev/null || true

  LAST_TAG=$(gh release view --repo project-koku/koku --json tagName,publishedAt \
    -q '"tagName=\(.tagName) publishedAt=\(.publishedAt)"' 2>/dev/null || echo "tagName=unknown publishedAt=")
  TAG_NAME=$(echo "$LAST_TAG" | sed 's/tagName=\([^ ]*\).*/\1/')
  PUBLISHED_AT=$(echo "$LAST_TAG" | sed 's/.*publishedAt=\(.*\)/\1/')

  PROD_SHA=$(get_prod_ref)

  SAFE_SHA=$(python3 "${KOKU_DIR}/dev/scripts/get-release-commit.py" 2>/dev/null \
    | grep -oE '[0-9a-f]{40}' | head -1 || true)
  HEAD_SHA="${SAFE_SHA:-$(git rev-parse origin/main)}"
  HEAD_SHORT="${HEAD_SHA:0:7}"

  LATEST_SHA=$(git rev-parse origin/main)
  COMMITS_AHEAD=0
  if [[ "$HEAD_SHA" != "$LATEST_SHA" ]]; then
    COMMITS_AHEAD=$(git log "${HEAD_SHA}..${LATEST_SHA}" --no-merges --oneline 2>/dev/null | wc -l | tr -d ' ')
  fi

  DAYS_AGO="unknown"
  if [[ -n "$PUBLISHED_AT" && "$PUBLISHED_AT" != "" ]]; then
    DAYS_AGO=$(python3 -c "
from datetime import datetime, timezone
published = datetime.fromisoformat('${PUBLISHED_AT}'.replace('Z','+00:00'))
now = datetime.now(timezone.utc)
print((now - published).days)
" 2>/dev/null || echo "?")
  fi

  COMMITS_SINCE_TAG=$(git log "${TAG_NAME}..origin/main" --no-merges --oneline 2>/dev/null | wc -l | tr -d ' ')
  COMMITS_SINCE_PROD=$(git log "${PROD_SHA}..origin/main" --no-merges --oneline 2>/dev/null | wc -l | tr -d ' ')

  COMMIT_LIST=$(git log "${PROD_SHA}..origin/main" --no-merges \
    --pretty=format:"  %h  %s" 2>/dev/null)

  PG_MIGRATIONS=$(check_pg_migrations "$PROD_SHA" "$HEAD_SHA")
  TRINO_MIGRATIONS=$(check_trino_migrations "$PROD_SHA" "$HEAD_SHA")
  PG_COUNT=0; [[ -n "$PG_MIGRATIONS" ]] && PG_COUNT=$(echo "$PG_MIGRATIONS" | wc -l | tr -d ' \t\n') || true
  TRINO_COUNT=0; [[ -n "$TRINO_MIGRATIONS" ]] && TRINO_COUNT=$(echo "$TRINO_MIGRATIONS" | wc -l | tr -d ' \t\n') || true

  MIGRATION_STATUS="none"
  (( PG_COUNT > 0 )) && MIGRATION_STATUS="pg" || true
  (( TRINO_COUNT > 0 )) && MIGRATION_STATUS="trino" || true
  (( PG_COUNT > 0 && TRINO_COUNT > 0 )) && MIGRATION_STATUS="pg+trino" || true

  COST_TICKETS=$(git log "${PROD_SHA}..origin/main" --no-merges --pretty=format:"%s" 2>/dev/null \
    | grep -oE 'COST-[0-9]+' | sort -u | paste -sd ', ' - || true)

  echo ""
  echo "╔══════════════════════════════════════════════════╗"
  echo "║        KOKU RELEASE READINESS REPORT            ║"
  echo "╚══════════════════════════════════════════════════╝"
  echo ""
  echo "   Koku dir         : ${KOKU_DIR}"
  echo "   App-interface dir: ${APP_INTERFACE_DIR}"
  echo ""

  echo "📦 LAST RELEASE"
  echo "   Tag        : ${TAG_NAME}"
  echo "   Published  : ${PUBLISHED_AT:-unknown}"
  echo "   Days ago   : ${DAYS_AGO} day(s)"
  echo ""

  echo "🔀 PENDING COMMITS"
  echo "   Prod ref   : ${PROD_SHA:0:12}..."
  echo "   HEAD (main): ${HEAD_SHORT}"
  echo "   Unreleased : ${COMMITS_SINCE_PROD} commit(s) since prod ref"
  echo "   Since tag  : ${COMMITS_SINCE_TAG} commit(s) since last GitHub release"
  echo ""

  if [[ -n "$COMMIT_LIST" ]]; then
    echo "   Commits to release:"
    echo "$COMMIT_LIST"
    echo ""
  fi

  echo "🗄  MIGRATIONS"
  if [[ "$MIGRATION_STATUS" == "none" ]]; then
    echo "   ✅ No migrations detected — deploy-only release"
  fi
  if (( PG_COUNT > 0 )); then
    echo "   ⚠️  PG Django migrations: ${PG_COUNT} file(s)"
    echo "      (team practice: run via DBM CJI MR before deploy; confirm with author)"
    echo "$PG_MIGRATIONS" | sed 's/^/      /'
  fi
  if (( TRINO_COUNT > 0 )); then
    echo "   🔴 Trino migrations: ${TRINO_COUNT} file(s) — MANUAL MR REQUIRED before deploy"
    echo "$TRINO_MIGRATIONS" | sed 's/^/      /'
  fi
  echo ""

  CI_CHECKS=$(gh api "repos/project-koku/koku/commits/${HEAD_SHA}/check-runs" \
    --jq '.check_runs[] | "\(.conclusion // "pending") \(.name)"' 2>/dev/null || true)

  CI_FAILED=$(echo "$CI_CHECKS" | grep "^failure" || true)
  CI_PENDING=$(echo "$CI_CHECKS" | grep "^pending\|^null" || true)

  echo "🧪 CI STATUS (${HEAD_SHORT})"
  if [[ -z "$CI_CHECKS" ]]; then
    echo "   (could not fetch CI status — check GitHub manually)"
  else
    echo "$CI_CHECKS" | while IFS= read -r line; do
      conclusion=$(echo "$line" | awk '{print $1}')
      name=$(echo "$line" | cut -d' ' -f2-)
      case "$conclusion" in
        success)  echo "   ✅ $name" ;;
        neutral)  echo "   ⚪ $name (skipped/neutral)" ;;
        failure)  echo "   ❌ $name  ← FAILED" ;;
        pending)  echo "   🔄 $name  (still running)" ;;
        *)        echo "   ❓ $name ($conclusion)" ;;
      esac
    done
    echo ""
    if [[ -n "$CI_FAILED" ]]; then
      echo "   ⚠️  FAILURES detected. Review before releasing:"
      echo "$CI_FAILED" | sed 's/failure /   ❌ /'
    fi
    if [[ -n "$CI_PENDING" ]]; then
      echo "   🔄 Some checks still running — consider waiting."
    fi
    if [[ -z "$CI_FAILED" && -z "$CI_PENDING" ]]; then
      echo "   ✅ All checks passed or skipped."
    fi
  fi
  echo ""

  echo "🎫 COST TICKETS"
  if [[ -n "$COST_TICKETS" ]]; then
    echo "   ${COST_TICKETS}"
  else
    echo "   (no COST tickets found in commit messages)"
  fi
  echo ""

  echo "──────────────────────────────────────────────────"
  echo "💡 SUGGESTED RELEASE"
  echo ""
  echo "   Suggested commit SHA : ${HEAD_SHA}"
  if [[ "$SAFE_SHA" == "$LATEST_SHA" ]]; then
    echo "   (latest commit — already validated by smoke tests)"
  else
    echo "   (last smoke-tested commit — ${COMMITS_AHEAD} newer commit(s) exist on main)"
    echo "   Latest on main       : ${LATEST_SHA:0:7} (not yet smoke-tested today)"
  fi
  echo "   Branch name          : hccm-prod-${HEAD_SHORT}"
  echo "   Commit message       : hccm: promote ${HEAD_SHORT} to prod"
  echo ""
  if [[ "$MIGRATION_STATUS" != "none" ]]; then
    echo "   ⚠️  Migration MR needed BEFORE deploy MR."
    echo "   Order: [migration MR + monitor] → [deploy MR]"
  else
    echo "   ✅ No migration MR needed. Proceed directly to deploy MR."
  fi
  echo "──────────────────────────────────────────────────"
  echo ""

  MIGRATION_LINE="No migrations in this release."
  if [[ "$MIGRATION_STATUS" == "pg" ]]; then
    MIGRATION_LINE="⚠️ PG migrations detected — plan DBM CJI MR before deploy (confirm with author)."
  elif [[ "$MIGRATION_STATUS" == "trino" ]]; then
    MIGRATION_LINE="🔴 Trino migrations detected — manual migration MR required before deploy."
  elif [[ "$MIGRATION_STATUS" == "pg+trino" ]]; then
    MIGRATION_LINE="🔴 PG + Trino migrations detected — migration MRs required before deploy."
  fi

  COMMIT_SUMMARY=$(git log "${PROD_SHA}..${HEAD_SHA}" --no-merges \
    --pretty=format:"  • %s" 2>/dev/null | head -10)

  echo "📣 SLACK MESSAGE — post in #crc-cost-mgmt-sre when starting:"
  echo "┌─────────────────────────────────────────────────"
  echo "│ 🚀 Starting cost-management release to production."
  echo "│ Promoting ${COMMITS_SINCE_PROD} commit(s): ${PROD_SHA:0:7} → ${HEAD_SHORT}"
  echo "│"
  echo "$COMMIT_SUMMARY" | sed 's/^/│ /'
  echo "│"
  echo "│ ${MIGRATION_LINE}"
  echo "└─────────────────────────────────────────────────"
  echo ""
  echo "❓ Do you want to proceed with this commit, or choose a different one?"
fi

if [[ "$cmd" == "migrations" ]]; then
  TARGET_SHA="${1:-}"
  if [[ -z "$TARGET_SHA" ]]; then
    echo "Usage: analyze.sh migrations <target-sha>"
    exit 1
  fi

  cd "$KOKU_DIR"
  git fetch origin -q 2>/dev/null || true

  PROD_SHA=$(get_prod_ref)
  PG_MIGRATIONS=$(check_pg_migrations "$PROD_SHA" "$TARGET_SHA")
  TRINO_MIGRATIONS=$(check_trino_migrations "$PROD_SHA" "$TARGET_SHA")
  PG_COUNT=$(echo "$PG_MIGRATIONS" | grep -c . 2>/dev/null || echo 0)
  TRINO_COUNT=$(echo "$TRINO_MIGRATIONS" | grep -c . 2>/dev/null || echo 0)

  echo ""
  echo "╔══════════════════════════════════════════════════╗"
  echo "║           MIGRATION CHECK                       ║"
  echo "╚══════════════════════════════════════════════════╝"
  echo "   From: ${PROD_SHA:0:12}  →  To: ${TARGET_SHA:0:12}"
  echo ""

  echo "── PG Django migrations ──"
  if [[ -n "$PG_MIGRATIONS" ]]; then
    echo "$PG_MIGRATIONS" | sed 's/^/   /'
    echo ""
    echo "   ⚠️  PG migrations found."
    echo "   Team practice: run them via a DBM CJI MR (DBM_IMAGE_TAG + DBM_INVOCATION)"
    echo "   before the deploy MR. Confirm with the migration author."
    echo "   Rare exception: author says init container alone is enough → deploy only."
  else
    echo "   (none)"
  fi

  echo ""
  echo "── Trino migrations ──"
  if [[ -n "$TRINO_MIGRATIONS" ]]; then
    echo "$TRINO_MIGRATIONS" | sed 's/^/   /'
    echo ""
    echo "   🔴 Trino migrations found — manual migration MR IS required."
    echo "   Order: migration MR → wait for 'Migrations Complete!' → deploy MR"
    echo "   Command: python koku/manage.py migrate_trino_tables --help"
  else
    echo "   (none)"
  fi

  echo ""
  echo "── Summary ──"
  echo "   PG migrations   : ${PG_COUNT} file(s)"
  echo "   Trino migrations: ${TRINO_COUNT} file(s)"
fi
