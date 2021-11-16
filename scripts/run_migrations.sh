#!/bin/bash

# The "scripts" dir should be a sibling to the "koku" dir that actually contains the app code
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
_APP_HOME=${APP_HOME:-$(dirname ${SCRIPT_DIR})/koku}

# Use a registered app name as arg 1 to constrain migrations to that app only
_APP="$1"
# Use a migration number (or full name minus the '.py')
# as arg 2 to execute up to (and including) the specified migration
# or to execute in reverse down to (but excluding) the specified migration
_MIGRATION="$2"

if [[ ( -z "${_APP}" ) && ( -z "${_MIGRATION}" ) ]]; then
    RESULT=$(python3.8 ${_APP_HOME}/manage.py check_migrations | tail -1)
else
    RESULT="False"
fi

if [[ "$RESULT" == "True" ]]; then
    echo "Migration already executed."
    RC=0
else
    if [[ "${DEVELOPMENT}" == "True" ]]; then
        export DJANGO_READ_DOT_ENV_FILE=True
    fi

    python3.8 ${_APP_HOME}/manage.py migrate_schemas ${_APP} ${_MIGRATION}
    RC=$?
fi

exit $RC
