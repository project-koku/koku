#!/usr/bin/env bash
# monitor.sh — Monitor koku deployment and migration jobs
#
# Usage:
#   monitor.sh deploy                          — watch koku pods
#   monitor.sh db-migration <tag> <invocation> — tail DB migration CJI logs
#   monitor.sh mgmt-cmd <tag> <invocation>     — tail management command CJI logs
#
# Requires: oc authenticated to the production cluster (koku-ci-management).

set -euo pipefail

cmd="${1:-}"
shift || true

check_oc_auth() {
  local whoami
  whoami=$(oc whoami 2>/dev/null || echo "system:anonymous")
  if [[ "$whoami" == "system:anonymous" || -z "$whoami" ]]; then
    echo "ERROR: Not authenticated to OpenShift cluster."
    echo ""
    echo "Authenticate via koku-ci-management (typical flow):"
    echo "  cd <path-to>/koku-ci/koku-ci-management"
    echo "  make login"
    echo "  eval \$(make env)"
    echo "  oc whoami   # should return your username, not system:anonymous"
    exit 1
  fi
  echo "Authenticated as: $whoami"
  echo ""
}

if [[ "$cmd" == "deploy" ]]; then
  check_oc_auth
  echo "Watching koku pods... (Ctrl+C to stop)"
  echo ""
  oc get pods -l app=koku -w

elif [[ "$cmd" == "db-migration" ]]; then
  IMAGE_TAG="${1:?Usage: monitor.sh db-migration <image-tag> <invocation>}"
  INVOCATION="${2:?Usage: monitor.sh db-migration <image-tag> <invocation>}"
  check_oc_auth
  echo "Tailing DB migration logs: koku-db-migrate-cji-${IMAGE_TAG}-${INVOCATION}"
  echo ""
  oc logs -l "job=koku-db-migrate-cji-${IMAGE_TAG}-${INVOCATION}" -f

elif [[ "$cmd" == "mgmt-cmd" ]]; then
  IMAGE_TAG="${1:?Usage: monitor.sh mgmt-cmd <image-tag> <invocation>}"
  INVOCATION="${2:?Usage: monitor.sh mgmt-cmd <image-tag> <invocation>}"
  check_oc_auth
  echo "Tailing management command logs: koku-management-command-cji-${IMAGE_TAG}-${INVOCATION}"
  echo ""
  oc logs -l "job=koku-management-command-cji-${IMAGE_TAG}-${INVOCATION}" --tail=-1 -f

else
  echo "Usage:"
  echo "  monitor.sh deploy"
  echo "  monitor.sh db-migration <image-tag> <invocation>"
  echo "  monitor.sh mgmt-cmd <image-tag> <invocation>"
  exit 1
fi
