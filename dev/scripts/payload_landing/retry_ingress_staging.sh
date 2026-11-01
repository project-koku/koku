#!/usr/bin/env bash
#
# Reset not_before/enqueued_at for a pending ingress staging row (local retry).
#
# Usage:
#   ./dev/scripts/payload_landing/retry_ingress_staging.sh <request_id>
#
set -euo pipefail

PAYLOAD_LANDING_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
DEV_SCRIPTS_PATH=$(cd -- "${PAYLOAD_LANDING_DIR}/.." &>/dev/null && pwd)
# shellcheck source=../common/logging.sh
source "${DEV_SCRIPTS_PATH}/common/logging.sh"

REQUEST_ID="${1:-}"
DB_CONTAINER="${DB_CONTAINER:-koku-db}"

if [[ -z "${REQUEST_ID}" ]]; then
    log-err "Usage: $(basename "$0") <request_id>"
    exit 2
fi

REQUEST_ID_ESCAPED=$(printf "%s" "${REQUEST_ID}" | sed "s/'/''/g")
docker exec "${DB_CONTAINER}" psql -U postgres -d postgres -c \
    "UPDATE reporting_common_ingress_staging_payload
     SET not_before = now(), enqueued_at = NULL
     WHERE request_id = '${REQUEST_ID_ESCAPED}' AND state = 'pending';"

log-info "Retry scheduled for request_id=${REQUEST_ID} (pending rows only)."
