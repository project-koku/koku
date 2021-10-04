#! /usr/bin/env bash

echo "Creating pg_stat_statements extension..."
psql -d $POSTGRES_DB -U $POSTGRES_USER -c "create extension if not exists pg_stat_statements;" 2>/dev/null

echo "Creating dbmonitor role..."
psql -d $POSTGRES_DB -U $POSTGRES_USER -c "create role dbmonitor with inherit login encrypted password 'dbmonitor' superuser in role $POSTGRES_USER;"



# from https://github.com/mrts/docker-postgresql-multiple-databases
function create_user_and_database() {
	local database=$1
	echo "  Creating user and database '$database'"
	psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
	    CREATE USER $database;
	    CREATE DATABASE $database;
	    GRANT ALL PRIVILEGES ON DATABASE $database TO $database;
EOSQL
}

if [ -n "$POSTGRES_MULTIPLE_DATABASES" ]; then
	echo "Multiple database creation requested: $POSTGRES_MULTIPLE_DATABASES"
	for db in $(echo $POSTGRES_MULTIPLE_DATABASES | tr ',' ' '); do
		create_user_and_database $db
	done
	echo "Multiple databases created"
fi
