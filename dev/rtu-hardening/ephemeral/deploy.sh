#!/usr/bin/env bash
#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
# Deploy the current branch to an ephemeral namespace with bonfire, without merging anything,
# and turn the RTU flag on in the namespace's Unleash. Full walkthrough: dev/rtu-hardening/README.md.
#
# Prerequisites: an `eph` kube context for the ephemeral cluster (~/bin/oc-token.sh eph --setup-context;
# no need to make it the current context), bonfire installed, and the branch pushed. The image comes from the
# Konflux build of a draft PR (KONFLUX_PR=<n>), or from your own public quay repo (QUAY_REPO=...).
#
# Usage, from the koku repository root:
#   KONFLUX_PR=<n> dev/rtu-hardening/ephemeral/deploy.sh wait-image   # until pr-<n>-<sha7> is on quay
#   QUAY_REPO=quay.io/<user>/koku dev/rtu-hardening/ephemeral/deploy.sh build   # alternative: build locally
#   dev/rtu-hardening/ephemeral/deploy.sh reserve                     # DURATION=12h by default
#   dev/rtu-hardening/ephemeral/deploy.sh secrets                     # no-op if koku-aws/koku-gcp exist
#   KONFLUX_PR=<n> dev/rtu-hardening/ephemeral/deploy.sh deploy       # or QUAY_REPO=... for a local build
#   dev/rtu-hardening/ephemeral/deploy.sh flag                        # FLAG=... for another flag
#   dev/rtu-hardening/ephemeral/deploy.sh release
# The reserved namespace is remembered in dev/rtu-hardening/ephemeral/.namespace (git-ignored).
set -euo pipefail

# Pin every cluster call to the ephemeral cluster's context (OC_CONTEXT, default "eph"), whatever the
# kubeconfig's current context is (other tools switch it). oc takes --context; bonfire has no such
# option and follows the current context, so it gets a temporary kubeconfig holding only OC_CONTEXT.
OC_CONTEXT="${OC_CONTEXT:-eph}"
oc() { command oc --context "${OC_CONTEXT}" "$@"; }
bonfire() {
    local kubeconfig rc=0
    kubeconfig="$(mktemp)"
    chmod 600 "${kubeconfig}"
    command oc config view --raw --minify --context "${OC_CONTEXT}" > "${kubeconfig}"
    KUBECONFIG="${kubeconfig}" command bonfire "$@" || rc=$?
    rm -f "${kubeconfig}"
    return "${rc}"
}

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${HERE}/../../.." && pwd)"
NS_FILE="${HERE}/.namespace"
FLAG="${FLAG:-cost-management.backend.cost_breakdown_rates_to_usage}"
SHA="$(git -C "${REPO_DIR}" rev-parse HEAD)"
TAG="$(git -C "${REPO_DIR}" rev-parse --short=7 HEAD)"

namespace() {
    [[ -s "${NS_FILE}" ]] || { echo "no namespace reserved; run: $0 reserve" >&2; exit 1; }
    cat "${NS_FILE}"
}

require_image() {
    [[ -n "${KONFLUX_PR:-}" || -n "${QUAY_REPO:-}" ]] \
        || { echo "set KONFLUX_PR=<pr number> or QUAY_REPO=quay.io/<user>/koku" >&2; exit 1; }
}

# Image to deploy: the Konflux PR build (KONFLUX_PR=<n>, tag pr-<n>-<short sha>, public, expires after 5 days)
# or a locally built image in QUAY_REPO (tag <short sha>).
KONFLUX_REPO="quay.io/redhat-user-workloads/cost-mgmt-dev-tenant/koku"
if [[ -n "${KONFLUX_PR:-}" ]]; then
    IMAGE="${KONFLUX_REPO}"
    IMAGE_TAG="pr-${KONFLUX_PR}-${TAG}"
else
    IMAGE="${QUAY_REPO:-}"
    IMAGE_TAG="${TAG}"
fi

case "${1:-}" in
build)
    [[ -n "${QUAY_REPO:-}" ]] || { echo "set QUAY_REPO=quay.io/<user>/koku (a public repo)" >&2; exit 1; }
    [[ -z "$(git -C "${REPO_DIR}" status --porcelain)" ]] || { echo "commit your changes first: the image tag is the commit" >&2; exit 1; }
    docker buildx build --platform linux/amd64 --build-arg GIT_COMMIT="${SHA}" \
        -t "${QUAY_REPO}:${TAG}" --push "${REPO_DIR}"
    echo "pushed ${QUAY_REPO}:${TAG}"
    ;;
wait-image)
    [[ -n "${KONFLUX_PR:-}" ]] || { echo "set KONFLUX_PR=<pr number>" >&2; exit 1; }
    url="https://quay.io/api/v1/repository/${KONFLUX_REPO#quay.io/}/tag/?specificTag=${IMAGE_TAG}"
    for _ in $(seq 1 90); do
        if curl -sf "${url}" | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin)["tags"] else 1)'; then
            echo "image ready: ${IMAGE}:${IMAGE_TAG}"
            exit 0
        fi
        sleep 60
    done
    echo "image ${IMAGE}:${IMAGE_TAG} not found after 90 minutes" >&2
    exit 1
    ;;
reserve)
    bonfire namespace reserve --duration "${DURATION:-12h}" > "${NS_FILE}"
    echo "reserved $(namespace)"
    ;;
secrets)
    # Reserved namespaces already carry koku-aws and koku-gcp (copied in at reservation); the
    # service-docs runbook's creds.txt step is only needed if they are missing.
    ns="$(namespace)"
    if oc get secret koku-aws koku-gcp -n "${ns}" > /dev/null 2>&1; then
        echo "koku-aws and koku-gcp already present in ${ns}; nothing to do"
        exit 0
    fi
    [[ -r "${CREDS_FILE:-}" ]] || { echo "secrets missing; set CREDS_FILE to the runbook's creds.txt" >&2; exit 1; }
    oc process -f "${REPO_DIR}/dev/secrets-template.yaml" --param-file="${CREDS_FILE}" -n "${ns}" \
        | oc create -f - -n "${ns}"
    ;;
deploy)
    # Everything from app-interface (current trino, rbac, ...); only koku's template ref and image
    # are overridden. Bonfire fetches the template from GitHub by full SHA, so push the branch first.
    # The two trino parameters (from the service-docs runbook) point Trino's hive catalog at AWS Glue:
    # ephemeral has no hive-metastore, and without them OCP processing fails in sync_hive_partitions.
    # SOURCES_BYPASS_RBAC=true (opt-in) turns off sources-api's RBAC check in this namespace only.
    # Needed while RBAC's /api/rbac/v1/access/ returns 404 in ephemeral (seen 2026-11-03): sources-api
    # then answers 500 to every source registration. Decide deliberately; see README "Known issues".
    # The migration job takes its image from DBM_IMAGE/DBM_IMAGE_TAG (default koku:latest, main's
    # migrations): without them the branch's own migrations never run and the workers wait for them
    # forever. A finished migration job does not run again under the same name; DBM_INVOCATION=01, 02,
    # ... names a new one, but Clowder starts it only once the koku app is ready (README "Known issues").
    require_image
    extra=()
    if [[ "${SOURCES_BYPASS_RBAC:-}" == "true" ]]; then
        extra+=(--set-parameter "sources-api/BYPASS_RBAC=true")
    fi
    bonfire process hccm \
        --source=appsre \
        --set-template-ref "koku=${SHA}" \
        --set-parameter "koku/IMAGE=${IMAGE}" \
        --set-parameter "koku/IMAGE_TAG=${IMAGE_TAG}" \
        --set-parameter "koku/DBM_IMAGE=${IMAGE}" \
        --set-parameter "koku/DBM_IMAGE_TAG=${IMAGE_TAG}" \
        --set-parameter "koku/DBM_INVOCATION=${DBM_INVOCATION:-00}" \
        ${extra[@]+"${extra[@]}"} \
        --set-parameter trino/HIVE_PROPERTIES_FILE=glue.properties \
        --set-parameter trino/GLUE_PROPERTIES_FILE=hive.properties \
        --no-remove-resources koku \
        --no-remove-resources trino \
        --namespace "$(namespace)" | oc apply -f - -n "$(namespace)"
    echo "deployed ${IMAGE}:${IMAGE_TAG} (template ${SHA})"
    ;;
flag)
    ns="$(namespace)"
    oc port-forward -n "${ns}" "service/env-${ns}-featureflags" 4242:4242 > /dev/null 2>&1 &
    pf=$!
    trap 'kill ${pf} 2>/dev/null || true' EXIT
    sleep 3
    jar="$(mktemp)"
    curl -sf -c "${jar}" -H 'Content-Type: application/json' \
        -d '{"username": "admin", "password": "unleash4all"}' http://localhost:4242/auth/simple/login > /dev/null
    api="http://localhost:4242/api/admin"
    curl -s -b "${jar}" -H 'Content-Type: application/json' -d "{\"name\": \"${FLAG}\", \"type\": \"release\"}" \
        "${api}/projects/default/features" > /dev/null || true
    for env in $(curl -sf -b "${jar}" "${api}/environments" | python3 -c 'import json,sys; print(" ".join(e["name"] for e in json.load(sys.stdin)["environments"]))'); do
        curl -s -b "${jar}" -H 'Content-Type: application/json' \
            -d '{"name": "flexibleRollout", "parameters": {"rollout": "100", "stickiness": "default", "groupId": "'"${FLAG}"'"}}' \
            "${api}/projects/default/features/${FLAG}/environments/${env}/strategies" > /dev/null || true
        curl -sf -b "${jar}" -X POST "${api}/projects/default/features/${FLAG}/environments/${env}/on" > /dev/null \
            && echo "enabled ${FLAG} in ${env}"
    done
    rm -f "${jar}"
    ;;
release)
    bonfire namespace release "$(namespace)" && rm -f "${NS_FILE}"
    ;;
*)
    sed -n '/^# Usage/,/^# The reserved/p' "$0"
    exit 1
    ;;
esac
