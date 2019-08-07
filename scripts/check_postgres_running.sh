#!/usr/bin/env bash
# Check that postgres is available for Koku use.
#
# Assumes environment variables have been set:
#   - POSTGRES_SQL_SERVICE_PORT
#   - POSTGRES_SQL_SERVICE_HOST

export PGPORT="${POSTGRES_SQL_SERVICE_PORT}"
export PGHOST="${POSTGRES_SQL_SERVICE_HOST}"

pg_isready || {
    PG_ISREADY_CODE=$?
    echo "CRITICAL: postgres is not running or environment is misconfigured"
    exit ${PG_ISREADY_CODE}
}
