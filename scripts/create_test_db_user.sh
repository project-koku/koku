#!/usr/bin/env bash
# Ensure Koku's postgres user exists as a superuser so Django can manage its test database.
#
# Assumes environment variables have been set:
#   - POSTGRES_SQL_SERVICE_PORT
#   - POSTGRES_SQL_SERVICE_HOST
#   - DATABASE_ADMIN (postgres admin user)
#   - DATABASE_PASSWORD (postgres admin user's password)
#   - DATABASE_USER (postgres user to be recreated)

export PGPASSWORD="${DATABASE_PASSWORD}"
export PGPORT="${POSTGRES_SQL_SERVICE_PORT}"
export PGHOST="${POSTGRES_SQL_SERVICE_HOST}"
export PGUSER="${DATABASE_ADMIN}"

dropuser -w --if-exists "${DATABASE_USER}" || \
    echo "NOTICE: Could not drop user '${DATABASE_USER}'"
createuser -w -s "${DATABASE_USER}" || \
    echo "NOTICE: Could not create user '${DATABASE_USER}'"
psql -w --quiet -d template1 \
    -c "ALTER USER ${DATABASE_USER} WITH PASSWORD '${DATABASE_PASSWORD}'"
