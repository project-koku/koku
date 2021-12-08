#!/bin/bash

# The "scripts" dir should be a sibling to the "koku" dir that actually contains the app code
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
_APP_HOME=${APP_HOME:-$(dirname ${SCRIPT_DIR})/koku}

declare -i RC=0
declare -i _HAS_MIG=0
declare -a _MIG_OPS=()

_NOOP="__NOOP__"


arg_check()
{
    # Command line args will override _MIGRATION_DIRECTIVE
    if [[ -n "$1" ]] ; then
        if [[ -n "$2" ]] ; then
            _MIGRATION_DIRECTIVE="${1}:${2}"
        else
            _MIGRATION_DIRECTIVE="${1}"
        fi
    fi
}


bash_check()
{
    local -i _rc=0
    local -i _chk_ver_major=${1:-4}
    local -i _chk_ver_minor=${2:-0}
    local _ver_str=""
    local -i _ver_major=0
    local -i _ver_minor=0

    _ver_str=$(bash --version | grep -E "version [0-9]+\." | sed -e 's/.*version //1' -e 's/ .x86.*$//1')
    _ver_major=${_ver_str%%.*}
    _ver_str=${_ver_str#*.}
    _ver_minor=${_ver_str%%.*}

    if [[ ${_ver_major} -ge ${_chk_ver_major} ]] ; then
        if [[ ${_ver_major} -eq ${_chk_ver_major} ]] ; then
            if [[ ${_ver_minor} -ge ${_chk_ver_minor} ]] ; then
                _rc=0
            else
                _rc=1
            fi
        else
            _rc=0
        fi
    else
        _rc=1
    fi

    if [[ $_rc -ne 0 ]] ; then
        echo "🚨 : ERROR ::  This script uses advanced bash ops. Please upgrade bash to version >= ${_chk_ver_major}.${_chk_ver_minor}" >&2
    fi

    return $_rc
}


# This will parse the information in the environment variable _MIGRATION_DIRECTIVE if any
# The parsed vales will be stored in the associative array _MIG_OPS.
# It will be indexed by the django app and its value will be the migration target
# _MIGRATION_DIRECTIVE will be empty or will have the form:
#     <app>,...
# or
#     <app>:<migration>,...
parse_directive()
{
    local _tmp _op

    if [[ -n "${_MIGRATION_DIRECTIVE}" ]]; then
        # Set terminating delimiter to ensure that parsing works correctly
        if [[ "${_MIGRATION_DIRECTIVE: -1}" != ',' ]]; then
            _tmp="${_MIGRATION_DIRECTIVE},"
        else
            _tmp="${_MIGRATION_DIRECTIVE}"
        fi

        while [[ -n "${_tmp}" ]]; do
            _op=${_tmp%%,*}
            _tmp=${_tmp#*,}

            # Attempt to detect an empty op (malformed directive)
            if [[ -z "${_op}" ]]; then
                break
            fi

            # If the op is app-only, then add a terminating delimiter
            if [[ ${_op} != *":"* ]]; then
                _op="${_op}:"
            fi

            # Set the flag to bypass the check if there is a migration specified
            [[ -n "${_op#*:}" ]] && _HAS_MIG=1

            # Store the op in the global array
            _MIG_OPS+=("${_op}")
        done
    else
        # If there are no directives, mark as NO-OP
        _MIG_OPS+=("${_NOOP}")
    fi
}


check_migrations()
{
    local -i _rc

    # If we have a specific migration, skip the migration check as this could be a downgrade op
    if [[ $_HAS_MIG -eq 0 ]]; then
        echo "🔎 : Checking to see if migrations should be run..."
        RESULT=$(python3.8 ${_APP_HOME}/manage.py check_migrations | tail -1)
    else
        RESULT="False"
    fi

    if [[ "${RESULT}" == "True" ]]; then
        echo "👍 : Migrations have already been processed"
        _rc=1
    elif [[ "${RESULT}" == "STOP" ]]; then
        echo "🛑 : Migrations are verifying or running"
        _rc=1  # set to bad exit code in case the image has differences from running image
    else
        echo "🤔 : Migrations should be run"
        _rc=0
    fi

    return $_rc
}


process_migrations()
{
    local -i _rc
    local _app _mig

    _rc=0

    if [[ "${DEVELOPMENT}" == "True" ]]; then
        export DJANGO_READ_DOT_ENV_FILE=True
    fi

    for _op in ${_MIG_OPS[@]}; do
        if [[ ${_op} != "${_NOOP}" ]]; then
            _app=${_op%%:*}
            _mig=${_op#*:}
        else
            _app=""
            _mig=""
        fi

        echo "⌚ : Running Migrations ${_app} ${_mig}"
        python3.8 ${_APP_HOME}/manage.py migrate_schemas ${_app} ${_mig}
        _rc=$?
        if [[ ${_rc} -ne 0 ]]; then
            echo "⛔ : ERROR (${_rc}) running migrations ${_app} ${_mig}" >&2
            break
        else
            echo "✅ : Migrations complete!"
        fi
    done

    return $_rc
}


export APPLICATION_NAME="koku_db_migration"

# Check to see if any CLI args will override the env var
arg_check $@

# Check to see if bash is compatible
if bash_check 4 4
then
    # Parse out the directive into an array of options
    parse_directive

    # Check to see if migrations should be run
    if check_migrations
    then
        # Execute migrations
        process_migrations
        RC=$?
    else
        # Ensure that a non-zero code never is forwarded from the check func
        RC=0
    fi
else
    # Error out on bash check fail
    RC=2
fi

export APPLICATION_NAME=koku


exit $RC
