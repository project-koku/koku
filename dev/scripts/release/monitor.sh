#!/usr/bin/env bash
# monitor.sh — Monitor koku deployment and migration jobs
#
# Usage:
#   monitor.sh deploy                          — poll koku pods until Ready
#   monitor.sh db-migration <tag> <invocation> — poll DB migration CJI until done
#   monitor.sh mgmt-cmd <tag> <invocation>     — poll management command CJI until done
#
# Env:
#   KOKU_PROD_NAMESPACE — OpenShift namespace (default: hccm-prod)
#   MONITOR_TIMEOUT     — seconds before giving up (default: 900)
#   MONITOR_POLL_SECONDS — poll interval (default: 15)
#
# Requires: oc authenticated to the production cluster (koku-ci-management).

set -euo pipefail

cmd="${1:-}"
shift || true

NAMESPACE="${KOKU_PROD_NAMESPACE:-hccm-prod}"
TIMEOUT="${MONITOR_TIMEOUT:-900}"
POLL_SECONDS="${MONITOR_POLL_SECONDS:-15}"

check_oc_auth() {
  local whoami project
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
  echo "Context: $(oc config current-context 2>/dev/null || echo unknown)"
  project=$(oc project -q 2>/dev/null || true)
  if [[ -n "${project}" && "${project}" != "${NAMESPACE}" ]]; then
    echo "Current project '${project}' != ${NAMESPACE}; switching..."
    oc project "${NAMESPACE}" >/dev/null
  fi
  echo "Namespace: ${NAMESPACE}"
  echo "Timeout: ${TIMEOUT}s (set MONITOR_TIMEOUT to change)"
  echo ""
}

pods_all_ready() {
  local selector="$1"
  local out
  out=$(oc get pods -n "${NAMESPACE}" -l "${selector}" --no-headers 2>/dev/null || true)
  if [[ -z "${out}" ]]; then
    return 1
  fi
  # Fail if any pod is not Running with Ready matching total, or Terminating
  echo "${out}" | awk '
    {
      ready=$2; status=$3
      split(ready, a, "/")
      if (status != "Running" || a[1] != a[2] || a[2] == 0) { bad=1 }
    }
    END { exit bad+0 }
  '
}

job_pods_terminal() {
  # Prints pod lines on stdout. Exit: 0=success, 1=still running/none, 2=failed
  local selector="$1"
  local out
  out=$(oc get pods -n "${NAMESPACE}" -l "${selector}" --no-headers 2>/dev/null || true)
  if [[ -z "${out}" ]]; then
    return 1
  fi
  echo "${out}"
  echo "${out}" | awk '
    $3 ~ /Completed|Succeeded/ { ok=1 }
    $3 ~ /Error|Failed|CrashLoop/ { fail=1 }
    END {
      if (fail) exit 2
      if (ok) exit 0
      exit 1
    }
  '
}

if [[ "$cmd" == "deploy" ]]; then
  check_oc_auth
  echo "Watching koku pods in ${NAMESPACE}..."
  echo ""
  deadline=$((SECONDS + TIMEOUT))
  while (( SECONDS < deadline )); do
    oc get pods -n "${NAMESPACE}" -l app=koku
    echo ""
    if pods_all_ready "app=koku"; then
      echo "✅ All koku pods are Running/Ready in ${NAMESPACE}"
      exit 0
    fi
    sleep "${POLL_SECONDS}"
  done
  echo "ERROR: timed out after ${TIMEOUT}s waiting for koku pods Ready" >&2
  exit 1

elif [[ "$cmd" == "db-migration" ]]; then
  IMAGE_TAG="${1:?Usage: monitor.sh db-migration <image-tag> <invocation>}"
  INVOCATION="${2:?Usage: monitor.sh db-migration <image-tag> <invocation>}"
  check_oc_auth
  SELECTOR="job=koku-db-migrate-cji-${IMAGE_TAG}-${INVOCATION}"
  echo "Monitoring DB migration: ${SELECTOR}"
  echo ""
  deadline=$((SECONDS + TIMEOUT))
  while (( SECONDS < deadline )); do
    set +e
    out=$(job_pods_terminal "${SELECTOR}")
    rc=$?
    set -e
    if [[ -n "${out}" ]]; then
      echo "${out}"
      echo ""
    else
      echo "   (no pods yet for ${SELECTOR})"
    fi
    if (( rc == 0 )); then
      echo "── Logs ──"
      oc logs -n "${NAMESPACE}" -l "${SELECTOR}" --tail=-1 || true
      echo ""
      echo "✅ DB migration job completed"
      exit 0
    fi
    if (( rc == 2 )); then
      echo "── Logs ──"
      oc logs -n "${NAMESPACE}" -l "${SELECTOR}" --tail=-1 || true
      echo ""
      echo "ERROR: DB migration job failed" >&2
      exit 1
    fi
    sleep "${POLL_SECONDS}"
  done
  echo "ERROR: timed out after ${TIMEOUT}s waiting for DB migration" >&2
  exit 1

elif [[ "$cmd" == "mgmt-cmd" ]]; then
  IMAGE_TAG="${1:?Usage: monitor.sh mgmt-cmd <image-tag> <invocation>}"
  INVOCATION="${2:?Usage: monitor.sh mgmt-cmd <image-tag> <invocation>}"
  check_oc_auth
  SELECTOR="job=koku-management-command-cji-${IMAGE_TAG}-${INVOCATION}"
  echo "Monitoring management command: ${SELECTOR}"
  echo ""
  deadline=$((SECONDS + TIMEOUT))
  while (( SECONDS < deadline )); do
    set +e
    out=$(job_pods_terminal "${SELECTOR}")
    rc=$?
    set -e
    if [[ -n "${out}" ]]; then
      echo "${out}"
      echo ""
    else
      echo "   (no pods yet for ${SELECTOR})"
    fi
    if (( rc == 0 )); then
      echo "── Logs ──"
      oc logs -n "${NAMESPACE}" -l "${SELECTOR}" --tail=-1 || true
      echo ""
      echo "✅ Management command job completed"
      exit 0
    fi
    if (( rc == 2 )); then
      echo "── Logs ──"
      oc logs -n "${NAMESPACE}" -l "${SELECTOR}" --tail=-1 || true
      echo ""
      echo "ERROR: management command job failed" >&2
      exit 1
    fi
    sleep "${POLL_SECONDS}"
  done
  echo "ERROR: timed out after ${TIMEOUT}s waiting for management command" >&2
  exit 1

else
  echo "Usage:"
  echo "  monitor.sh deploy"
  echo "  monitor.sh db-migration <image-tag> <invocation>"
  echo "  monitor.sh mgmt-cmd <image-tag> <invocation>"
  echo ""
  echo "Env: KOKU_PROD_NAMESPACE (default hccm-prod), MONITOR_TIMEOUT (default 900)"
  exit 1
fi
