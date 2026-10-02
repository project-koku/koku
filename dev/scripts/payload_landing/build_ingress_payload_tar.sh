#!/usr/bin/env bash
#
# Build a flat-root OCP ingress tarball for Kafka payload-landing local tests.
# Not run in tox/CI by default.
#
# Usage:
#   ./dev/scripts/payload_landing/build_ingress_payload_tar.sh -s 2026-09-01 -e 2026-09-30
#
# Optional environment variables:
#   CLUSTER_ID     default my-ocp-cluster-1
#   OUTPUT_DIR     default /tmp/ingress-payloads
#   NISE_OUTPUT    default /tmp/nise_ocp_output
#   NISE_YAML      default dev/scripts/nise_ymls/ocp_on_aws/ocp_static_data.yml
#
set -euo pipefail

PAYLOAD_LANDING_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
DEV_SCRIPTS_PATH=$(cd -- "${PAYLOAD_LANDING_DIR}/.." &>/dev/null && pwd)
KOKU_ROOT=$(cd -- "${DEV_SCRIPTS_PATH}/../.." &>/dev/null && pwd)
# shellcheck source=../common/logging.sh
source "${DEV_SCRIPTS_PATH}/common/logging.sh"

CLUSTER_ID="${CLUSTER_ID:-my-ocp-cluster-1}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp/ingress-payloads}"
NISE_OUTPUT="${NISE_OUTPUT:-/tmp/nise_ocp_output}"
NISE_YAML="${NISE_YAML:-${KOKU_ROOT}/dev/scripts/nise_ymls/ocp_on_aws/ocp_static_data.yml}"
START_DATE=""
END_DATE=""

usage() {
    log-info "Usage: $(basename "$0") -s YYYY-MM-DD -e YYYY-MM-DD"
    exit 2
}

while getopts ":s:e:h" opt; do
    case "${opt}" in
        s) START_DATE="${OPTARG}" ;;
        e) END_DATE="${OPTARG}" ;;
        h) usage ;;
        *) usage ;;
    esac
done

if [[ -z "${START_DATE}" || -z "${END_DATE}" ]]; then
    usage
fi

RENDERED_YAML="/tmp/ocp_static_data.yml"
mkdir -p "${OUTPUT_DIR}" "${NISE_OUTPUT}"

log-info "Rendering nise yaml (${START_DATE} .. ${END_DATE})"
(cd "${KOKU_ROOT}" && pipenv run python dev/scripts/render_nise_yamls.py \
    -f "${NISE_YAML}" \
    -o "${RENDERED_YAML}" \
    -s "${START_DATE}" \
    -e "${END_DATE}")

log-info "Running nise (cluster ${CLUSTER_ID})"
(cd "${KOKU_ROOT}" && \
    S3_ACCESS_KEY="${S3_ACCESS_KEY:-s4admin}" \
    S3_SECRET_KEY="${S3_SECRET_KEY:-s4secret}" \
    S3_BUCKET_NAME="${S3_BUCKET_NAME:-ocp-ingress}" \
    pipenv run nise report ocp \
    --static-report-file "${RENDERED_YAML}" \
    --ocp-cluster-id "${CLUSTER_ID}" \
    --insights-upload "${NISE_OUTPUT}" \
    --daily-reports)

MONTH_DIR=$(find "${NISE_OUTPUT}/${CLUSTER_ID}" -mindepth 1 -maxdepth 1 -type d | head -1)
if [[ -z "${MONTH_DIR}" || ! -d "${MONTH_DIR}" ]]; then
    log-err "No month directory under ${NISE_OUTPUT}/${CLUSTER_ID}"
    exit 1
fi

TARBALL="${OUTPUT_DIR}/payload.tar.gz"
export COPYFILE_DISABLE=1
tar czf "${TARBALL}" -C "${MONTH_DIR}" $(ls -A "${MONTH_DIR}")

if ! tar tzf "${TARBALL}" | grep -qE '^manifest\.json$'; then
    log-err "Tarball missing manifest.json at archive root: ${TARBALL}"
    exit 1
fi

log-info "Wrote ${TARBALL}"
log-info "Serve with: ${PAYLOAD_LANDING_DIR}/serve_ingress_payload.sh ${OUTPUT_DIR}"
