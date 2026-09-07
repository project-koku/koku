#!/usr/bin/env bash
# monitor-mr.sh — Monitor GitLab MR status via API, or guide manual monitoring
#
# Usage:
#   monitor-mr.sh <source-branch>
#
# Requires: GITLAB_PAT env var (api scope token from gitlab.cee.redhat.com)
# Falls back to manual instructions if PAT is missing or VPN unreachable.

set -euo pipefail

BRANCH="${1:?Usage: monitor-mr.sh <source-branch>}"

GITLAB_BASE="https://gitlab.cee.redhat.com/api/v4"
PROJECT_ID="13582"   # service/app-interface
POLL_INTERVAL=30

MR_WEB_URL="https://gitlab.cee.redhat.com/service/app-interface/-/merge_requests"

GITLAB_PAT="${GITLAB_PAT:-${GITLAB_TOKEN:-}}"

if [[ -z "${GITLAB_PAT:-}" ]]; then
  echo ""
  echo "⚠️  GITLAB_PAT not set — cannot monitor MR automatically."
  echo ""
  echo "To enable automatic monitoring, generate a token:"
  echo "  1. Go to: https://gitlab.cee.redhat.com/-/user_settings/personal_access_tokens"
  echo "  2. Name: release-automation | Scope: api | Save"
  echo "  3. Add to your shell profile: export GITLAB_PAT=\"glpat-xxxx\""
  echo "  4. Reload the shell"
  echo ""
  echo "────────────────── MANUAL INSTRUCTIONS ──────────────────"
  echo "  1. Open: ${MR_WEB_URL}?scope=created_by_me&state=opened"
  echo "  2. Find MR for branch: ${BRANCH}"
  echo "  3. Post in #crc-cost-mgmt-sre: ping @crc-cost-mgmt-dev for review"
  echo "  4. Wait for reviewer to post /lgtm"
  echo "  5. app-sre-bot will merge automatically after /lgtm"
  echo "  6. Come back here and confirm: 'MR was merged'"
  echo "──────────────────────────────────────────────────────────"
  exit 0
fi

HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
  "${GITLAB_BASE}/projects/${PROJECT_ID}" \
  -H "Authorization: Bearer ${GITLAB_PAT}" 2>/dev/null || echo "000")

if [[ "$HTTP_STATUS" != "200" ]]; then
  echo ""
  echo "⚠️  Cannot reach gitlab.cee.redhat.com (HTTP ${HTTP_STATUS})."
  echo "   Make sure you are connected to the Red Hat VPN."
  echo ""
  echo "────────────────── MANUAL INSTRUCTIONS ──────────────────"
  echo "  1. Open: ${MR_WEB_URL}?scope=created_by_me&state=opened"
  echo "  2. Find MR for branch: ${BRANCH}"
  echo "  3. Post in #crc-cost-mgmt-sre: ping @crc-cost-mgmt-dev for review"
  echo "  4. Wait for /lgtm and automatic merge by app-sre-bot"
  echo "  5. Confirm here when merged"
  echo "──────────────────────────────────────────────────────────"
  exit 1
fi

echo ""
echo "🔍 Looking for MR with source branch: ${BRANCH}"

MR_DATA=$(curl -s --max-time 10 \
  "${GITLAB_BASE}/projects/${PROJECT_ID}/merge_requests?source_branch=${BRANCH}&state=opened" \
  -H "Authorization: Bearer ${GITLAB_PAT}" 2>/dev/null)

MR_IID=$(echo "$MR_DATA" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data:
    print(data[0]['iid'])
else:
    print('')
" 2>/dev/null || echo "")

if [[ -z "$MR_IID" ]]; then
  MR_DATA=$(curl -s --max-time 10 \
    "${GITLAB_BASE}/projects/${PROJECT_ID}/merge_requests?source_branch=${BRANCH}" \
    -H "Authorization: Bearer ${GITLAB_PAT}" 2>/dev/null)
  MR_IID=$(echo "$MR_DATA" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data:
    print(data[0]['iid'])
else:
    print('')
" 2>/dev/null || echo "")
fi

if [[ -z "$MR_IID" ]]; then
  echo ""
  echo "❌ No MR found for branch '${BRANCH}'."
  echo "   Make sure the branch was pushed and the MR was opened."
  echo "   Open: ${MR_WEB_URL}/new?merge_request[source_branch]=${BRANCH}"
  exit 1
fi

MR_URL=$(echo "$MR_DATA" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data: print(data[0]['web_url'])
" 2>/dev/null || echo "${MR_WEB_URL}/${MR_IID}")

echo "   Found MR !${MR_IID}: ${MR_URL}"
echo ""
echo "⏳ Polling every ${POLL_INTERVAL}s until merged (Ctrl+C to stop)..."
echo ""

ATTEMPT=0
while true; do
  ATTEMPT=$((ATTEMPT + 1))
  TIMESTAMP=$(date '+%H:%M:%S')

  STATE=$(curl -s --max-time 10 \
    "${GITLAB_BASE}/projects/${PROJECT_ID}/merge_requests/${MR_IID}" \
    -H "Authorization: Bearer ${GITLAB_PAT}" 2>/dev/null | \
    python3 -c "import sys,json; print(json.load(sys.stdin).get('state','unknown'))" 2>/dev/null || echo "error")

  case "$STATE" in
    merged)
      echo ""
      echo "✅ [${TIMESTAMP}] MR !${MR_IID} was merged!"
      echo "   ${MR_URL}"
      exit 0
      ;;
    closed)
      echo ""
      echo "❌ [${TIMESTAMP}] MR !${MR_IID} was closed (not merged)."
      echo "   Check: ${MR_URL}"
      exit 1
      ;;
    opened)
      LABELS=$(curl -s --max-time 10 \
        "${GITLAB_BASE}/projects/${PROJECT_ID}/merge_requests/${MR_IID}" \
        -H "Authorization: Bearer ${GITLAB_PAT}" 2>/dev/null | \
        python3 -c "
import sys, json
d = json.load(sys.stdin)
labels = d.get('labels', [])
approvals = d.get('upvotes', 0)
print(f'labels={labels} upvotes={approvals}')
" 2>/dev/null || echo "")
      echo "   [${TIMESTAMP}] Still open... ${LABELS}"
      ;;
    error)
      echo "   [${TIMESTAMP}] API error — retrying..."
      ;;
    *)
      echo "   [${TIMESTAMP}] State: ${STATE}"
      ;;
  esac

  sleep "$POLL_INTERVAL"
done
