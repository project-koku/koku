#!/usr/bin/env bash
#
# Serve a directory over HTTP for the listener to download test tarballs.
#
# Usage:
#   ./dev/scripts/payload_landing/serve_ingress_payload.sh [directory] [port]
#
# Defaults: /tmp/ingress-payloads 8765
#
set -euo pipefail

PAYLOAD_LANDING_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
DEV_SCRIPTS_PATH=$(cd -- "${PAYLOAD_LANDING_DIR}/.." &>/dev/null && pwd)
# shellcheck source=../common/logging.sh
source "${DEV_SCRIPTS_PATH}/common/logging.sh"

SERVE_DIR="${1:-/tmp/ingress-payloads}"
PORT="${2:-8765}"

if [[ ! -d "${SERVE_DIR}" ]]; then
    log-err "Directory does not exist: ${SERVE_DIR}"
    exit 1
fi

log-info "Serving ${SERVE_DIR} on port ${PORT} (Ctrl+C to stop)."
log-info "From a container on koku_default:"
log-info "  docker run --rm --network koku_default curlimages/curl:latest -sfI \"http://host.docker.internal:${PORT}/payload.tar.gz\" | head -3"

exec python3 -m http.server "${PORT}" --directory "${SERVE_DIR}"
