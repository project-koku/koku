#!/usr/bin/env bash
# Verify the authorization matrix against a running koku.
#
#   scripts/rbac_v2_lab/verify.sh
#
# Expects:
#   - koku running on $KOKU_URL (default http://localhost:8002)
#   - the org seeded (seed.sh) and opted into RBAC v2
#   - env.sh sourced, or the same variables exported
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=env.sh
. "$SCRIPT_DIR/env.sh"

KOKU_URL="${KOKU_URL:-http://localhost:8002}"
API="${KOKU_URL}/api/v1"
QUERY="filter%5Btime_scope_value%5D=-1&filter%5Btime_scope_units%5D=month&filter%5Bresolution%5D=monthly"

FAILED=0

check() {
  local identity=$1 path=$2 expected=$3 label=$4
  local code
  code=$(curl -sS -o /dev/null -w '%{http_code}' \
    -H "x-rh-identity: ${identity}" \
    "${API}/${path}/?${QUERY}") || code="000"
  if [[ "$code" == "$expected" ]]; then
    printf 'PASS  %-45s %s (expected %s)\n' "$label" "$code" "$expected"
  else
    printf 'FAIL  %-45s %s (expected %s)\n' "$label" "$code" "$expected"
    FAILED=1
  fi
}

echo "koku: ${KOKU_URL}   rbac: ${RBAC_URL}   org: ${LAB_ORG_ID}"
echo

check "$USER1_IDENTITY" "reports/openshift/costs" 200 "user1  openshift costs"
check "$USER1_IDENTITY" "reports/aws/costs" 200 "user1  aws costs"
check "$USER1_IDENTITY" "reports/openshift/infrastructures/aws/costs" 200 "user1  ocp-on-aws costs"
check "$USER2_IDENTITY" "reports/openshift/costs" 200 "user2  openshift costs"
check "$USER2_IDENTITY" "reports/aws/costs" 403 "user2  aws costs"
check "$USER2_IDENTITY" "reports/openshift/infrastructures/aws/costs" 403 "user2  ocp-on-aws costs"

echo
if [[ "$FAILED" -ne 0 ]]; then
  echo "matrix FAILED"
  exit 1
fi
echo "matrix OK"
