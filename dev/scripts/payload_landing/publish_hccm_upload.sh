#!/usr/bin/env bash
#
# Publish a synthetic HCCM upload announce message to local Kafka.
# Not run in tox/CI by default.
#
# Usage:
#   ./dev/scripts/payload_landing/publish_hccm_upload.sh <request_id>
#
# Optional environment variables:
#   PAYLOAD_URL   default http://host.docker.internal:8765/payload.tar.gz
#   ACCOUNT       default 10001
#   ORG_ID        default 1234567
#   KAFKA_CONTAINER default koku-kafka
#
set -euo pipefail

PAYLOAD_LANDING_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
DEV_SCRIPTS_PATH=$(cd -- "${PAYLOAD_LANDING_DIR}/.." &>/dev/null && pwd)
# shellcheck source=../common/logging.sh
source "${DEV_SCRIPTS_PATH}/common/logging.sh"

REQUEST_ID="${1:-}"
if [[ -z "${REQUEST_ID}" ]]; then
    log-err "Usage: $(basename "$0") <request_id>"
    exit 2
fi

PAYLOAD_URL="${PAYLOAD_URL:-http://host.docker.internal:8765/payload.tar.gz}"
ACCOUNT="${ACCOUNT:-10001}"
ORG_ID="${ORG_ID:-1234567}"
KAFKA_CONTAINER="${KAFKA_CONTAINER:-koku-kafka}"

if ! docker inspect -f '{{.State.Running}}' "${KAFKA_CONTAINER}" 2>/dev/null | grep -q true; then
    log-err "Kafka container ${KAFKA_CONTAINER} is not running. Run: make docker-up-payload-landing"
    exit 1
fi

payload=$(REQUEST_ID="${REQUEST_ID}" PAYLOAD_URL="${PAYLOAD_URL}" ACCOUNT="${ACCOUNT}" ORG_ID="${ORG_ID}" python3 - <<'PY'
import json
import os

print(
    json.dumps(
        {
            "request_id": os.environ["REQUEST_ID"],
            "account": os.environ["ACCOUNT"],
            "org_id": os.environ["ORG_ID"],
            "url": os.environ["PAYLOAD_URL"],
            "b64_identity": "dGVzdA==",
            "size": 1,
        }
    )
)
PY
)

printf 'service:hccm\t%s\n' "${payload}" | docker exec -i "${KAFKA_CONTAINER}" \
    kafka-console-producer \
    --bootstrap-server kafka:29092 \
    --topic platform.upload.announce \
    --property parse.headers=true

log-info "Published request_id=${REQUEST_ID} to platform.upload.announce"
