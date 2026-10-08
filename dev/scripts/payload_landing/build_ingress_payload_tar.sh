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

export NISE_OUTPUT CLUSTER_ID START_DATE END_DATE
MONTH_DIR=$(
    python3 - <<'PY'
import json
import os

cluster_path = os.path.join(os.environ["NISE_OUTPUT"], os.environ["CLUSTER_ID"])
start_date = os.environ["START_DATE"]
end_date = os.environ["END_DATE"]

matches = []
if os.path.isdir(cluster_path):
    for name in os.listdir(cluster_path):
        report_dir = os.path.join(cluster_path, name)
        manifest_path = os.path.join(report_dir, "manifest.json")
        if not os.path.isdir(report_dir) or not os.path.isfile(manifest_path):
            continue
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
        if manifest.get("start", "")[:10] == start_date and manifest.get("end", "")[:10] == end_date:
            matches.append(report_dir)

if matches:
    matches.sort(key=lambda path: os.path.getmtime(path), reverse=True)
    print(matches[0])
PY
)

if [[ -z "${MONTH_DIR}" || ! -d "${MONTH_DIR}" ]]; then
    if [[ "$(uname -s)" == "Darwin" ]]; then
        PERIOD_START=$(date -j -f "%Y-%m-%d" "${START_DATE}" "+%Y%m01")
        PERIOD_END=$(date -j -v+1m -f "%Y%m%d" "${PERIOD_START}" "+%Y%m01")
    else
        PERIOD_START=$(date -d "${START_DATE}" "+%Y%m01")
        PERIOD_END=$(date -d "${PERIOD_START} +1 month" "+%Y%m01")
    fi
    MONTH_DIR="${NISE_OUTPUT}/${CLUSTER_ID}/${PERIOD_START}-${PERIOD_END}"
fi

if [[ -z "${MONTH_DIR}" || ! -d "${MONTH_DIR}" ]]; then
    log-err "No report directory for ${START_DATE} .. ${END_DATE} under ${NISE_OUTPUT}/${CLUSTER_ID}"
    exit 1
fi

TARBALL="${OUTPUT_DIR}/payload.tar.gz"
export COPYFILE_DISABLE=1
tar czf "${TARBALL}" -C "${MONTH_DIR}" .

if ! tar tzf "${TARBALL}" | grep -qE '^(\./)?manifest\.json$'; then
    log-err "Tarball missing manifest.json at archive root: ${TARBALL}"
    exit 1
fi

log-info "Wrote ${TARBALL}"
log-info "Serve with: ${PAYLOAD_LANDING_DIR}/serve_ingress_payload.sh ${OUTPUT_DIR}"
