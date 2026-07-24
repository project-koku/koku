#!/usr/bin/env bash
#
# Optional Koku S3 object-store smoke test.
#
# Validates that a running S3-compatible backend (S4 local dev) supports the operations
# Koku relies on. This is NOT a unit test and is NOT run in tox/CI by default.
#
# Backend-agnostic: configure via environment variables. Works against S4 or any S3-compatible store.
#
# Usage:
#   export S3_ENDPOINT=http://localhost:9000   # host; omit to use this default
#   export S3_ACCESS_KEY=s4admin
#   export S3_SECRET=s4secret
#   ./dev/scripts/s3_smoke_test.sh
#
# Optional:
#   CONTAINER_RUNTIME=docker|podman   force aws-cli container runtime (auto-detected by default)
#
# Delete this file if the team decides integration smoke tests are not needed.
#
set -euo pipefail

DEV_SCRIPTS_PATH=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
KOKU_ROOT=$(cd -- "${DEV_SCRIPTS_PATH}/../.." &>/dev/null && pwd)

source "${DEV_SCRIPTS_PATH}/common/logging.sh"
source "${DEV_SCRIPTS_PATH}/common/utils.sh"

# Defaults match S4 local dev (see docker-compose.yml).
S3_ENDPOINT="${S3_ENDPOINT:-http://localhost:9000}"
S3_ACCESS_KEY="${S3_ACCESS_KEY:-s4admin}"
S3_SECRET="${S3_SECRET:-s4secret}"
AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
KOKU_BUCKET="${S3_BUCKET_NAME:-koku-bucket}"
OCP_BUCKET="${S3_BUCKET_NAME_OCP_INGRESS:-ocp-ingress}"
METASTORE_BUCKET="${S3_METASTORE_BUCKET:-metastore}"

S3_HOST_ENDPOINT="$(normalize_host_s3_endpoint "${S3_ENDPOINT}")"

endpoint_port() {
    local endpoint=$1
    if [[ "${endpoint}" =~ :([0-9]+)(/|$|\?) ]]; then
        echo "${BASH_REMATCH[1]}"
    elif [[ "${endpoint}" == https://* ]]; then
        echo 443
    else
        echo 80
    fi
}

S3_ENDPOINT_PORT="$(endpoint_port "${S3_HOST_ENDPOINT}")"

export AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY}"
export AWS_SECRET_ACCESS_KEY="${S3_SECRET}"
export AWS_DEFAULT_REGION

AWS_CLI_IMAGE="${AWS_CLI_IMAGE:-docker.io/amazon/aws-cli:latest}"
PASSED=0
FAILED=0

CONTAINER_RT=""
AWS_CLI_NETWORK_MODE=""
AWS_CLI_ENDPOINT=""
AWS_CLI_BRIDGE_ARGS=()

container_runtime() {
    if [[ -n "${CONTAINER_RUNTIME:-}" ]]; then
        if command -v "${CONTAINER_RUNTIME}" &>/dev/null \
            && "${CONTAINER_RUNTIME}" info &>/dev/null 2>&1; then
            echo "${CONTAINER_RUNTIME}"
            return
        fi
        echo ""
        return
    fi

    # Prefer the runtime that is actually running local S4.
    if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
        if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'koku-s4'; then
            echo docker
            return
        fi
    fi
    if command -v podman &>/dev/null && podman info &>/dev/null 2>&1; then
        if podman ps --format '{{.Names}}' 2>/dev/null | grep -qx 'koku-s4'; then
            echo podman
            return
        fi
    fi

    # Fall back to any reachable runtime (Docker/Rancher before Podman).
    if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
        echo docker
    elif command -v podman &>/dev/null && podman info &>/dev/null 2>&1; then
        echo podman
    else
        echo ""
    fi
}

aws_cli_probe() {
    local network_mode=$1
    local endpoint_url=$2
    shift 2
    local -a extra_args=("$@")
    local err_file
    err_file=$(mktemp)
    local -a run_args=(run --rm)
    if [[ "${network_mode}" == host ]]; then
        run_args+=(--network host)
    else
        run_args+=("${extra_args[@]}")
    fi
    run_args+=(
        -e AWS_ACCESS_KEY_ID
        -e AWS_SECRET_ACCESS_KEY
        -e AWS_DEFAULT_REGION
        "${AWS_CLI_IMAGE}"
        --endpoint-url "${endpoint_url}"
        s3 ls
    )
    if "${CONTAINER_RT}" "${run_args[@]}" >"${err_file}" 2>&1; then
        rm -f "${err_file}"
        return 0
    fi
    rm -f "${err_file}"
    return 1
}

configure_aws_cli_network() {
    local port="${S3_ENDPOINT_PORT}"
    local -a candidates=()

    # Linux Docker, Podman, and Rancher Desktop usually reach published ports via host networking.
    candidates+=("host|${S3_HOST_ENDPOINT}|")

    # Docker Desktop / some VM-backed runtimes expose the host via host-gateway aliases.
    if [[ "${CONTAINER_RT}" == docker ]]; then
        candidates+=(
            "bridge|http://host.docker.internal:${port}|--add-host=host.docker.internal:host-gateway"
        )
    fi
    if [[ "${CONTAINER_RT}" == podman ]]; then
        candidates+=(
            "bridge|http://host.containers.internal:${port}|--add-host=host.containers.internal:host-gateway"
        )
    fi

    local candidate spec mode endpoint extra
    for candidate in "${candidates[@]}"; do
        IFS='|' read -r mode endpoint extra <<<"${candidate}"
        if aws_cli_probe "${mode}" "${endpoint}" ${extra:+"${extra}"}; then
            AWS_CLI_NETWORK_MODE="${mode}"
            AWS_CLI_ENDPOINT="${endpoint}"
            if [[ "${mode}" == bridge && -n "${extra}" ]]; then
                AWS_CLI_BRIDGE_ARGS=(${extra})
            else
                AWS_CLI_BRIDGE_ARGS=()
            fi
            log-info "aws-cli network: ${mode}, endpoint: ${AWS_CLI_ENDPOINT}"
            return 0
        fi
    done
    return 1
}

aws_cli() {
    local -a run_args=(run --rm)
    if [[ "${AWS_CLI_NETWORK_MODE}" == host ]]; then
        run_args+=(--network host)
    else
        run_args+=("${AWS_CLI_BRIDGE_ARGS[@]}")
    fi
    run_args+=(
        -e AWS_ACCESS_KEY_ID
        -e AWS_SECRET_ACCESS_KEY
        -e AWS_DEFAULT_REGION
        "${AWS_CLI_IMAGE}"
        --endpoint-url "${AWS_CLI_ENDPOINT}"
    )
    "${CONTAINER_RT}" "${run_args[@]}" "$@"
}

# Host bind mounts into the aws-cli container are unreliable on some Docker runtimes
# (e.g. Rancher Desktop virtiofs). Use stdin/stdout for object bodies instead.
aws_cli_upload_file() {
    local local_path=$1
    local s3_uri=$2
    shift 2
    local -a run_args=(run --rm -i)
    if [[ "${AWS_CLI_NETWORK_MODE}" == host ]]; then
        run_args+=(--network host)
    else
        run_args+=("${AWS_CLI_BRIDGE_ARGS[@]}")
    fi
    run_args+=(
        -e AWS_ACCESS_KEY_ID
        -e AWS_SECRET_ACCESS_KEY
        -e AWS_DEFAULT_REGION
        "${AWS_CLI_IMAGE}"
        --endpoint-url "${AWS_CLI_ENDPOINT}"
        s3 cp - "${s3_uri}"
    )
    cat "${local_path}" | "${CONTAINER_RT}" "${run_args[@]}" "$@"
}

aws_cli_download_file() {
    local s3_uri=$1
    local local_path=$2
    aws_cli s3 cp "${s3_uri}" - > "${local_path}"
}

pass() {
    PASSED=$((PASSED + 1))
    log-info "PASS: $*"
}

fail() {
    FAILED=$((FAILED + 1))
    log-err "FAIL: $*"
}

check_endpoint_reachable() {
    log-info "Checking S3 endpoint from host: ${S3_HOST_ENDPOINT}"
    if curl -sf "${S3_HOST_ENDPOINT}/" >/dev/null 2>&1 \
        || curl -sf "${S3_HOST_ENDPOINT}" >/dev/null 2>&1; then
        pass "endpoint reachable from host"
    else
        log-err "Cannot reach ${S3_HOST_ENDPOINT} from the host"
        log-err "Start object storage first, e.g.:"
        log-err "  make docker-up-min-trino-no-build"
        log-err "If port 9000 is in use (frontend), run: lsof -ti :9000 | xargs kill"
        exit 1
    fi

    log-info "Checking S3 endpoint from aws-cli container"
    if ! configure_aws_cli_network; then
        log-err "aws-cli container cannot reach S3 at ${S3_HOST_ENDPOINT}"
        log-err "Tried host networking and bridge host-gateway aliases."
        log-err "Set CONTAINER_RUNTIME=docker or CONTAINER_RUNTIME=podman if auto-detection picked the wrong runtime."
        exit 1
    fi
    pass "endpoint reachable from aws-cli container"
}

python_for_presigned_test() {
    if [[ -n "${VIRTUAL_ENV:-}" ]] && command -v python &>/dev/null; then
        echo python
    elif command -v python3 &>/dev/null; then
        echo python3
    elif [[ -f "${KOKU_ROOT}/Pipfile" ]] && command -v pipenv &>/dev/null; then
        echo "pipenv"
    else
        echo ""
    fi
}

run_python_presigned() {
    local python_runner=$1
    shift
    if [[ "${python_runner}" == "pipenv" ]]; then
        PIPENV_DOTENV=0 pipenv run python "$@"
    else
        "${python_runner}" "$@"
    fi
}

require_bucket() {
    local bucket=$1
    if aws_cli s3 ls "s3://${bucket}" &>/dev/null; then
        pass "bucket exists: ${bucket}"
        return 0
    fi
    fail "bucket missing or not accessible: ${bucket}"
    return 1
}

test_buckets() {
    log-info "Test: required buckets"
    require_bucket "${KOKU_BUCKET}" || true
    require_bucket "${OCP_BUCKET}" || true
    require_bucket "${METASTORE_BUCKET}" || true
}

test_put_get_list_delete() {
    log-info "Test: PUT, GET, LIST, DELETE"
    local test_key="smoke-test/$(date +%s).txt"
    local test_body="koku-s3-smoke-test"
    local tmp_dir tmp_upload tmp_download
    tmp_dir=$(mktemp -d)
    tmp_upload="${tmp_dir}/upload"
    tmp_download="${tmp_dir}/download"
    printf '%s' "${test_body}" > "${tmp_upload}"

    if ! aws_cli_upload_file "${tmp_upload}" "s3://${KOKU_BUCKET}/${test_key}" &>/dev/null; then
        fail "PUT object"
        rm -rf "${tmp_dir}"
        return
    fi
    pass "PUT object"

    if ! aws_cli_download_file "s3://${KOKU_BUCKET}/${test_key}" "${tmp_download}" &>/dev/null; then
        fail "GET object"
        rm -rf "${tmp_dir}"
        return
    fi
    local downloaded
    downloaded=$(cat "${tmp_download}")
    rm -rf "${tmp_dir}"
    if [[ "${downloaded}" != "${test_body}" ]]; then
        fail "GET object content mismatch (expected '${test_body}', got '${downloaded}')"
        return
    fi
    pass "GET object"

    if ! aws_cli s3 ls "s3://${KOKU_BUCKET}/smoke-test/" 2>/dev/null | grep -q "${test_key##*/}"; then
        fail "LIST prefix"
        return
    fi
    pass "LIST prefix"

    if ! aws_cli s3 rm "s3://${KOKU_BUCKET}/${test_key}" &>/dev/null; then
        fail "DELETE object"
        return
    fi
    pass "DELETE object"
}

test_metadata() {
    log-info "Test: object user-metadata (manifestid)"
    local meta_key="smoke-test/meta-$(date +%s).bin"
    local tmp_empty
    tmp_empty=$(mktemp)
    : > "${tmp_empty}"

    if ! aws_cli_upload_file "${tmp_empty}" "s3://${KOKU_BUCKET}/${meta_key}" \
        --metadata manifestid=12345,reportdatestart=2026-01-01 &>/dev/null; then
        fail "PUT object with metadata"
        rm -f "${tmp_empty}"
        return
    fi
    rm -f "${tmp_empty}"

    local head_output
    if ! head_output=$(aws_cli s3api head-object --bucket "${KOKU_BUCKET}" --key "${meta_key}" 2>/dev/null); then
        fail "head-object for metadata"
        aws_cli s3 rm "s3://${KOKU_BUCKET}/${meta_key}" &>/dev/null || true
        return
    fi

    # RGW may lowercase metadata keys in responses.
    if echo "${head_output}" | grep -qi 'manifestid'; then
        pass "metadata round-trip (manifestid present)"
    else
        fail "metadata round-trip (manifestid not found in head-object output)"
        log-err "head-object output: ${head_output}"
    fi

    aws_cli s3 rm "s3://${KOKU_BUCKET}/${meta_key}" &>/dev/null || true
}

test_presigned_urls() {
    log-info "Test: presigned PUT + GET (boto3 — same path as ingest_ocp_payload)"

    local python_cmd
    python_cmd=$(python_for_presigned_test)
    if [[ -z "${python_cmd}" ]]; then
        fail "presigned URLs (no python available)"
        return
    fi

    # Presigned URLs are exercised from the host; use the host-reachable endpoint.
    if ! (
        export S3_ENDPOINT="${S3_HOST_ENDPOINT}"
        export S3_ACCESS_KEY="${S3_ACCESS_KEY}"
        export S3_SECRET="${S3_SECRET}"
        export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION}"
        export OCP_BUCKET="${OCP_BUCKET}"
        run_python_presigned "${python_cmd}" -
    ) <<'PY'
import os
import sys

import boto3
import requests

endpoint = os.environ["S3_ENDPOINT"]
bucket = os.environ["OCP_BUCKET"]
key = f"smoke-test/presigned-{int(__import__('time').time())}"
body = b"koku-s3-smoke-presigned"

client = boto3.client(
    "s3",
    endpoint_url=endpoint,
    aws_access_key_id=os.environ["S3_ACCESS_KEY"],
    aws_secret_access_key=os.environ["S3_SECRET"],
    region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
)

put_url = client.generate_presigned_url(
    "put_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=3600
)
get_url = client.generate_presigned_url(
    "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=3600
)

put_response = requests.put(put_url, data=body, timeout=30)
put_response.raise_for_status()
get_response = requests.get(get_url, timeout=30)
get_response.raise_for_status()
if get_response.content != body:
    print(f"content mismatch: {get_response.content!r}", file=sys.stderr)
    sys.exit(1)

# Cleanup via authenticated client
client.delete_object(Bucket=bucket, Key=key)
PY
    then
        fail "presigned PUT + GET round-trip"
        return
    fi
    pass "presigned PUT + GET round-trip"
}

main() {
    log-info "S3 smoke test — host endpoint: ${S3_HOST_ENDPOINT}"
    log-info "Buckets: ${KOKU_BUCKET}, ${OCP_BUCKET}, ${METASTORE_BUCKET}"

    CONTAINER_RT="$(container_runtime)"
    if [[ -z "${CONTAINER_RT}" ]]; then
        if [[ -n "${CONTAINER_RUNTIME:-}" ]]; then
            log-err "CONTAINER_RUNTIME=${CONTAINER_RUNTIME} is not available"
        else
            log-err "A working container runtime is required (docker or podman)"
            log-err "Start Rancher Desktop / Docker, or rootless Podman, then retry."
        fi
        exit 1
    fi
    log-info "Using container runtime: ${CONTAINER_RT}"

    check_endpoint_reachable
    test_buckets
    test_put_get_list_delete
    test_metadata
    test_presigned_urls

    log-info "Results: ${PASSED} passed, ${FAILED} failed"
    if [[ "${FAILED}" -gt 0 ]]; then
        exit 1
    fi
    log-info "All smoke tests passed."
}

main "$@"
