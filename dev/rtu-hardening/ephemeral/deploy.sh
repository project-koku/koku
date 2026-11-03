#!/usr/bin/env bash
#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
# Deploy the current branch to an ephemeral namespace with bonfire, without a PR:
# build the image locally, push it to your own (public) quay repo, deploy that image,
# and turn the RTU flag on in the namespace's Unleash.
# Follows service-docs docs/Testing/ephemeral-envs.md ("Deploy a Branch").
#
# Prerequisites: VPN, `oc login` to the ephemeral cluster (crc-eph), bonfire installed,
# docker logged in to quay.io, and the ephemeral secrets file from the runbook.
#
# Usage, from the koku repository root. Image from the Konflux build of the draft PR:
#   KONFLUX_PR=<n> dev/rtu-hardening/ephemeral/deploy.sh wait-image
#   KONFLUX_PR=<n> dev/rtu-hardening/ephemeral/deploy.sh config
# or built locally into your own public quay repo:
#   QUAY_REPO=quay.io/<user>/koku dev/rtu-hardening/ephemeral/deploy.sh build
#   QUAY_REPO=quay.io/<user>/koku dev/rtu-hardening/ephemeral/deploy.sh config
#   dev/rtu-hardening/ephemeral/deploy.sh reserve            # DURATION=12h by default
#   CREDS_FILE=/path/to/creds.txt dev/rtu-hardening/ephemeral/deploy.sh secrets
#   dev/rtu-hardening/ephemeral/deploy.sh deploy
#   dev/rtu-hardening/ephemeral/deploy.sh flag               # FLAG=... to choose another flag
#   dev/rtu-hardening/ephemeral/deploy.sh release
# The reserved namespace is remembered in dev/rtu-hardening/ephemeral/.namespace (git-ignored).
set -euo pipefail

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

require_quay() {
    [[ -n "${QUAY_REPO:-}" ]] || { echo "set QUAY_REPO, e.g. quay.io/<user>/koku, or KONFLUX_PR=<pr number>" >&2; exit 1; }
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
    require_quay
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
config)
    [[ -n "${KONFLUX_PR:-}" ]] || require_quay
    # Local component: bonfire reads deploy/clowdapp.yaml from REPO_DIR and takes the commit from its HEAD.
    sed -e "s#repo: project-koku/koku#repo: ${REPO_DIR}#" \
        -e "s#ref: <insert-commit>#ref: ${SHA}#" \
        -e "s#IMAGE_TAG: <insert-tag>#IMAGE_TAG: ${IMAGE_TAG}\n        IMAGE: ${IMAGE}\n        ENHANCED_ORG_ADMIN: True#" \
        "${REPO_DIR}/dev/config.yaml.local-example" > "${REPO_DIR}/dev/config.yaml"
    echo "wrote dev/config.yaml for ${IMAGE}:${IMAGE_TAG}"
    ;;
reserve)
    bonfire namespace reserve --duration "${DURATION:-12h}" > "${NS_FILE}"
    echo "reserved $(namespace)"
    ;;
secrets)
    [[ -r "${CREDS_FILE:-}" ]] || { echo "set CREDS_FILE to the ephemeral secrets file" >&2; exit 1; }
    oc process -f "${REPO_DIR}/dev/secrets-template.yaml" --param-file="${CREDS_FILE}" -n "$(namespace)" \
        | oc create -f - -n "$(namespace)"
    ;;
deploy)
    bonfire process hccm \
        --source=appsre \
        --local-config-path "${REPO_DIR}/dev/config.yaml" \
        --no-remove-resources koku \
        --no-remove-resources trino \
        --set-parameter trino/HIVE_PROPERTIES_FILE=glue.properties \
        --set-parameter trino/GLUE_PROPERTIES_FILE=hive.properties \
        --set-parameter rbac/MIN_REPLICAS=1 \
        --namespace "$(namespace)" | oc apply -f - -n "$(namespace)"
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
