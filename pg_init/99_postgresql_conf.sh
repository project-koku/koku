#! /usr/bin/env bash

echo "Creating pg_stat_statements extension..."
psql -d $POSTGRES_DB -U $POSTGRES_USER -c "create extension if not exists pg_stat_statements;" 2>/dev/null

echo "Creating dbmonitor role..."
psql -d $POSTGRES_DB -U $POSTGRES_USER -c "create role dbmonitor with inherit login encrypted password 'dbmonitor' superuser in role $POSTGRES_USER;"


create_user() {
    local rc=0
    local res

    res=$(psql -At -d ${POSTGRES_DB} -U ${POSTGRES_USER} -c "select oid from pg_roles where rolname = '${1}'")
    if [[ -z "$res" ]]
    then
        echo "Creating user \"${1}\"..."
        createuser --username=${POSTGRES_USER} --echo "${1}"
        rc=$?
    else
        echo "User \"${1}\" already exists."
        rc=2
    fi

    return $rc
}


create_db() {
    local rc=0
    local res

    res=$(psql -At -d ${POSTGRES_DB} -U ${POSTGRES_USER} -c "select oid from pg_database where datname = '${1}'")
    if [[ -z "$res" ]]
    then
        echo "Creating database \"${1}\" owned by \"${2}\"..."
        createdb --user=${POSTGRES_USER} --echo --owner="${2}" "${1}"
        rc=$?
    else
        echo "Database \"${1}\" already exists."
        rc=2
    fi

    return $rc
}


# Parse $_PG_CREATE_DATABASES by ',' into a bash array variable -- "dbname|owner,dbname|owner..."
IFS=, read -a _databases <<<${_PG_CREATE_DATABASES}
for _database in ${_databases[@]}
do
    # parse $_database by '|' into discrete variables -- "dbname|owner"
    IFS='|' read _dbname _owner <<<${_database}
    create_user "${_owner}"
    create_db "${_dbname}" "${_owner}"
done
