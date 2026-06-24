#!/usr/bin/env bash
#
# Verify the hybrid local object-storage setup:
#   - S4 (host :9000) — OCP ingress bucket
#   - MinIO (host :9001) — Trino/Hive parquet warehouse (koku-bucket)
#   - Long nested S3 keys fail on S4 but succeed on MinIO (known S4 limitation)
#
# Prerequisites: make docker-up-min-trino-no-build  (or trino-stack-up)
#
# Usage:
#   ./dev/scripts/s3_hybrid_verify.sh
#
set -euo pipefail

# logging.sh uses tput; force a color-capable TERM (dumb/empty breaks set -e on source).
export TERM=xterm

DEV_SCRIPTS_PATH=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
source "${DEV_SCRIPTS_PATH}/common/logging.sh"

S4_ENDPOINT="${S4_ENDPOINT:-http://localhost:9000}"
S4_ACCESS_KEY="${S3_ACCESS_KEY:-s4admin}"
S4_SECRET="${S3_SECRET:-s4secret}"

MINIO_ENDPOINT="${TRINO_S3_ENDPOINT:-http://localhost:9001}"
MINIO_ENDPOINT="${MINIO_ENDPOINT/koku-minio/localhost}"
MINIO_ENDPOINT="${MINIO_ENDPOINT/:9000/:9001}"
MINIO_ACCESS_KEY="${TRINO_S3_ACCESS_KEY:-kokuminioaccess}"
MINIO_SECRET="${TRINO_S3_SECRET:-kokuminiosecret}"

AWS_CLI_IMAGE="${AWS_CLI_IMAGE:-docker.io/amazon/aws-cli:latest}"
PASSED=0
FAILED=0

container_runtime() {
    if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
        echo docker
    elif command -v podman &>/dev/null && podman info &>/dev/null 2>&1; then
        echo podman
    else
        echo ""
    fi
}

CONTAINER_RT="$(container_runtime)"

aws_cli() {
    local endpoint=$1 access_key=$2 secret_key=$3
    shift 3
    "${CONTAINER_RT}" run --rm --network host \
        -e "AWS_ACCESS_KEY_ID=${access_key}" \
        -e "AWS_SECRET_ACCESS_KEY=${secret_key}" \
        -e AWS_DEFAULT_REGION=us-east-1 \
        "${AWS_CLI_IMAGE}" \
        --endpoint-url "${endpoint}" \
        "$@"
}

aws_cli_upload_stdin() {
    local endpoint=$1 access_key=$2 secret_key=$3 s3_uri=$4
    "${CONTAINER_RT}" run --rm -i --network host \
        -e "AWS_ACCESS_KEY_ID=${access_key}" \
        -e "AWS_SECRET_ACCESS_KEY=${secret_key}" \
        -e AWS_DEFAULT_REGION=us-east-1 \
        "${AWS_CLI_IMAGE}" \
        --endpoint-url "${endpoint}" \
        s3 cp - "${s3_uri}"
}

pass() {
    PASSED=$((PASSED + 1))
    log-info "PASS: $*"
}

fail() {
    FAILED=$((FAILED + 1))
    log-err "FAIL: $*"
}

check_service() {
    local name=$1 endpoint=$2
    if curl -sf "${endpoint}/" >/dev/null 2>&1 || curl -sf "${endpoint}" >/dev/null 2>&1 \
        || curl -sf "${endpoint}/minio/health/live" >/dev/null 2>&1; then
        pass "${name} reachable at ${endpoint}"
        return 0
    fi
    fail "${name} not reachable at ${endpoint}"
    return 1
}

test_bucket_crud() {
    local label=$1 endpoint=$2 access_key=$3 secret_key=$4 bucket=$5
    local key="hybrid-verify/$(date +%s).txt"
    local body="hybrid-verify-${label}"

    log-info "CRUD test on ${label} (${bucket})"
    if ! aws_cli "${endpoint}" "${access_key}" "${secret_key}" \
        s3api head-bucket --bucket "${bucket}" &>/dev/null; then
        fail "${label}: bucket ${bucket} missing"
        return
    fi
    pass "${label}: bucket ${bucket} exists"

    if ! printf '%s' "${body}" | aws_cli_upload_stdin "${endpoint}" "${access_key}" "${secret_key}" \
        "s3://${bucket}/${key}" &>/dev/null; then
        fail "${label}: PUT failed"
        return
    fi
    pass "${label}: PUT short key"

    local downloaded
    if ! downloaded=$(aws_cli "${endpoint}" "${access_key}" "${secret_key}" \
        s3 cp "s3://${bucket}/${key}" - 2>/dev/null | tr -d '\n'); then
        fail "${label}: GET failed"
        return
    fi
    if [[ "${downloaded}" != "${body}" ]]; then
        fail "${label}: GET content mismatch"
        return
    fi
    pass "${label}: GET short key"

    aws_cli "${endpoint}" "${access_key}" "${secret_key}" \
        s3 rm "s3://${bucket}/${key}" &>/dev/null || true
    pass "${label}: DELETE short key"
}

# Key shape similar to Trino/Hive partitioned Parquet writes (long nested path).
LONG_S3_KEY='data/my_schema.db/managed_azure_openshift_daily_temp/source=8ba56bc4-b48a-4f65-9962-68feae3bb477/ocp_source=c16d833f-7513-4289-a2df-9f5a2f9cb66b/year=2026/month=05/day=1/20260623_131922_00578_j34au_a76de11d-c2fd-4e40-885c-eb1daab59f74'

test_long_key() {
    local label=$1 endpoint=$2 access_key=$3 secret_key=$4 bucket=$5 expect_success=$6

    log-info "Long-key test on ${label} (expect success=${expect_success})"
    if printf 'long-key-test' | aws_cli_upload_stdin "${endpoint}" "${access_key}" "${secret_key}" \
        "s3://${bucket}/${LONG_S3_KEY}" &>/dev/null; then
        if [[ "${expect_success}" == "true" ]]; then
            pass "${label}: long nested key PUT succeeded (expected)"
            aws_cli "${endpoint}" "${access_key}" "${secret_key}" \
                s3 rm "s3://${bucket}/${LONG_S3_KEY}" &>/dev/null || true
        else
            fail "${label}: long nested key PUT succeeded (expected failure — S4 bug may be fixed?)"
        fi
    else
        if [[ "${expect_success}" == "false" ]]; then
            pass "${label}: long nested key PUT failed (expected — ENAMETOOLONG on S4)"
        else
            fail "${label}: long nested key PUT failed (unexpected)"
        fi
    fi
}

main() {
    log-info "Hybrid S3 verification"
    log-info "S4:    ${S4_ENDPOINT} (ocp-ingress)"
    log-info "MinIO: ${MINIO_ENDPOINT} (koku-bucket / Trino)"

    if [[ -z "${CONTAINER_RT}" ]]; then
        log-err "docker or podman required"
        exit 1
    fi

    check_service "S4" "${S4_ENDPOINT}" || true
    check_service "MinIO" "${MINIO_ENDPOINT}" || true

    test_bucket_crud "S4" "${S4_ENDPOINT}" "${S4_ACCESS_KEY}" "${S4_SECRET}" "ocp-ingress"
    test_bucket_crud "MinIO" "${MINIO_ENDPOINT}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET}" "koku-bucket"

    test_long_key "S4" "${S4_ENDPOINT}" "${S4_ACCESS_KEY}" "${S4_SECRET}" "ocp-ingress" "false"
    test_long_key "MinIO" "${MINIO_ENDPOINT}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET}" "koku-bucket" "true"

    log-info "Results: ${PASSED} passed, ${FAILED} failed"
    if [[ "${FAILED}" -gt 0 ]]; then
        exit 1
    fi
    log-info "Hybrid object storage verification passed."
}

main "$@"
