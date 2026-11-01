#!/usr/bin/env bash
#
# Summarize local ingress payload-landing state (Kafka, listener, S4, Postgres).
# Not run in tox/CI by default.
#
set -euo pipefail

PAYLOAD_LANDING_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
DEV_SCRIPTS_PATH=$(cd -- "${PAYLOAD_LANDING_DIR}/.." &>/dev/null && pwd)
# shellcheck source=../common/logging.sh
source "${DEV_SCRIPTS_PATH}/common/logging.sh"

KAFKA_CONTAINER="${KAFKA_CONTAINER:-koku-kafka}"
LISTENER_CONTAINER="${LISTENER_CONTAINER:-koku_listener}"
DB_CONTAINER="${DB_CONTAINER:-koku-db}"
S4_ENDPOINT="${S4_ENDPOINT:-http://koku-s4-proxy:7480}"
S3_ACCESS_KEY="${S3_ACCESS_KEY:-s4admin}"
S3_SECRET="${S3_SECRET:-s4secret}"
KOKU_BUCKET="${S3_BUCKET_NAME:-koku-bucket}"
LISTENER_LOG_MINUTES="${LISTENER_LOG_MINUTES:-5}"

missing=0
require_running() {
    local name=$1
    if ! docker inspect -f '{{.State.Running}}' "${name}" 2>/dev/null | grep -q true; then
        log-err "Container ${name} is not running."
        missing=1
    fi
}

require_running "${KAFKA_CONTAINER}"
require_running "${LISTENER_CONTAINER}"
if [[ "${missing}" -ne 0 ]]; then
    log-err "Run: make docker-up-payload-landing"
    exit 1
fi

log-info "Kafka consumer group hccm-group (platform.upload.announce):"
docker exec "${KAFKA_CONTAINER}" kafka-consumer-groups \
    --bootstrap-server kafka:29092 --describe --group hccm-group 2>/dev/null | grep -E 'platform.upload.announce|TOPIC' || true

log-info "Listener log hints (last ${LISTENER_LOG_MINUTES}m):"
docker logs "${LISTENER_CONTAINER}" --since "${LISTENER_LOG_MINUTES}m" 2>&1 | grep -E \
    'Processing message offset|ingress payload stored|ingress payload already stored|Seeking back|UNKNOWN_TOPIC|Unable to stage' || \
    log-warn "No matching listener log lines in the last ${LISTENER_LOG_MINUTES}m."

log-info "S4 ingress_staging objects (prefix data/ingress_staging/):"
docker run --rm --network koku_default \
    -e AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY}" -e AWS_SECRET_ACCESS_KEY="${S3_SECRET}" \
    amazon/aws-cli:latest \
    --endpoint-url "${S4_ENDPOINT}" \
    s3 ls "s3://${KOKU_BUCKET}/data/ingress_staging/" --recursive 2>/dev/null || \
    log-warn "Could not list S4 (is the stack up and network koku_default available?)."

if docker inspect -f '{{.State.Running}}' "${DB_CONTAINER}" 2>/dev/null | grep -q true; then
    log-info "Recent reporting_common_ingress_staging_payload rows:"
    docker exec "${DB_CONTAINER}" psql -U postgres -d postgres -c \
        "SELECT request_id, state, attempts, cluster_id, s3_key IS NOT NULL AS has_key,
                payload IS NULL AS payload_cleared, left(last_error, 120) AS last_error
         FROM reporting_common_ingress_staging_payload
         ORDER BY stored_at DESC NULLS LAST LIMIT 5;"
else
    log-warn "Database container ${DB_CONTAINER} not running; skipping staging table query."
fi
