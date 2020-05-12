#! /usr/bin/env bash

echo "Creating pg_stat_statements extension..."
psql -d $POSTGRES_DB -U $POSTGRES_USER -c "create extension if not exists pg_stat_statements;" 2>/dev/null

echo "Creating dbmonitor role..."
psql -d $POSTGRES_DB -U $POSTGRES_USER -c "create role dbmonitor with inherit login encrypted password 'dbmonitor' superuser in role $POSTGRES_USER;"
