#!/bin/bash

# The "scripts" dir should be a sibling to the "koku" dir that actually contains the app code
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
_APP_HOME=${APP_HOME:-$(dirname ${SCRIPT_DIR})/koku}

declare -i _HAS_MIG=0
declare -a _MIG_OPS


# This will parse the information in the environment variable _MIGRATION_DIRECTIVE if any
# The parsed vales will be stored in the associative array _MIG_OPS.
# It will be indexed by the django app and its value will be the migration target
# _MIGRATION_DIRECTIVE will be empty or will have the form:
#     <app>,...
# or
#     <app>:<migration>,...
parse_directive()
{
    local _tmp _app _mig _op

    if [[ -n "${_MIGRATION_DIRECTIVE}" ]]; then
        if [[ "${_MIGRATION_DIRECTIVE: -1}" != ',' ]]; then
            _tmp="${_MIGRATION_DIRECTIVE},"
        else
            _tmp="${_MIGRATION_DIRECTIVE}"
        fi

        while [[ -n "${_tmp}" ]]; do
            _op=${_tmp%%,*}
            _tmp=${_tmp#*,}

            if [[ -z "${_op}" ]]; then
                break
            fi

            if [[ ${_op} != *":"* ]]; then
                _op="${_op}:"
            fi

            [[ -n "${_op#*:}" ]] && _HAS_MIG=1

            _MIG_OPS+=("${_op}")
        done
    else
        _MIG_OPS+=("_NOOP_")
    fi
}


check_migrations()
{
    local _rc

    if [[ $_HAS_MIG -eq 0 ]]; then
        RESULT=$(python3.8 ${_APP_HOME}/manage.py check_migrations | tail -1)
    else
        RESULT="False"
    fi

    if [[ "${RESULT}" == "True" ]]; then
        echo "Migrations have already been processed"
        _rc=1
    else
        _rc=0
    fi

    return $_rc
}


process_migrations()
{
    if [[ "${DEVELOPMENT}" == "True" ]]; then
        export DJANGO_READ_DOT_ENV_FILE=True
    fi

    for _op in ${_MIG_OPS[@]}; do
        if [[ ${_op} == "__NOOP__" ]]; then
            _app=${_op%%:*}
            _mig=${_op#*:}
        else
            _app=""
            _mig=""
        fi

        echo "Running Migrations ${_app} ${_mig}"
        python3.8 ${_APP_HOME}/manage.py migrate_schemas ${_app} ${_mig}
        RC=$?
        if [[ ${RC} -ne 0 ]]; then
            echo "ERROR (${RC}) running migrations ${_app} ${_mig}"
            break
        fi
    done
}


parse_directive

if check_migrations
then
    process_migrations
    RC=$?
else
    RC=0
fi

# if [[ $_HAS_MIG -eq 0 ]]; then
#     echo "Checking if migrations need to be processed."
#     RESULT=$(python3.8 ${_APP_HOME}/manage.py check_migrations | tail -1)
# else
#     RESULT="False"
# fi

# if [[ "$RESULT" == "True" ]]; then
#     echo "Migrations already processed."
#     RC=0
# else
#     if [[ "${DEVELOPMENT}" == "True" ]]; then
#         export DJANGO_READ_DOT_ENV_FILE=True
#     fi

#     for _op in ${_MIG_OPS[@]}; do
#         _app=${_op%%:*}
#         _mig=${_op#*:}

#         echo "Running Migration ${_app} ${_mig}"
#         python3.8 ${_APP_HOME}/manage.py migrate_schemas ${_app} ${_mig}
#         RC=$?
#         if [[ ${RC} -ne 0 ]]; then
#             echo "ERROR (${RC}) running migration ${_app} ${_mig}"
#             break
#         fi
#     done
# fi

exit $RC
