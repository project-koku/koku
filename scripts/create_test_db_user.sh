#!/usr/bin/env bash
# Recreate the Koku database and user.
#
# Assumes environment variables have been set:
#   - POSTGRES_SQL_SERVICE_PORT
#   - POSTGRES_SQL_SERVICE_HOST
#   - DATABASE_ADMIN (postgres admin user)
#   - DATABASE_PASSWORD (postgres admin user's password)
#   - DATABASE_USER (postgres user to be recreated)
#   - DATABASE_NAME (postgres database to be recreated)

export PGPASSWORD="${DATABASE_PASSWORD}"
export PGPORT="${POSTGRES_SQL_SERVICE_PORT}"
export PGHOST="${POSTGRES_SQL_SERVICE_HOST}"
export PGUSER="${DATABASE_ADMIN}"

dropuser -w --if-exists "${DATABASE_USER}" || \
    echo "NOTICE: Could not drop user '${DATABASE_USER}'"
dropdb -w --if-exists "${DATABASE_NAME}" || \
    echo "NOTICE: Could not drop database '${DATABASE_NAME}'"

# Chain the following commands because they must *all* succeed,
# or else this script must exit with non-zero code.
createdb -w "${DATABASE_NAME}" && \
createuser -w -s "${DATABASE_USER}" && \
psql -w --quiet -d "${DATABASE_NAME}" \
    -c "ALTER USER ${DATABASE_USER} WITH PASSWORD '${DATABASE_PASSWORD}'"
