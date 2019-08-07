#!/usr/bin/env bash
# Drop the Koku database user.
#
# Assumes environment variables have been set:
#   - POSTGRES_SQL_SERVICE_PORT
#   - POSTGRES_SQL_SERVICE_HOST
#   - DATABASE_ADMIN (postgres admin user)
#   - DATABASE_PASSWORD (postgres admin user's password)
#   - DATABASE_USER (postgres user to be dropped)

export PGPASSWORD="${DATABASE_PASSWORD}"
export PGPORT="${POSTGRES_SQL_SERVICE_PORT}"
export PGHOST="${POSTGRES_SQL_SERVICE_HOST}"
export PGUSER="${DATABASE_ADMIN}"

dropuser -w --if-exists "${DATABASE_USER}" || \
    echo "WARNING: Could not drop user '${DATABASE_USER}'"
