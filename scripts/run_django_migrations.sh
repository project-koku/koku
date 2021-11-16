#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# The "scripts" dir should be a sibling to the "koku" dir that actually contains the app code
cd $(dirname ${SCRIPT_DIR})/koku

# Leave _APP and _MIGRATION unset to execute any migrations for all apps
# Use a registered app name as arg 1 to constrain migrations to that app only
_APP="$1"
# Use a migration number (or full name minus the '.py')
# as arg 2 to execute up to (and including) the specified migration
# or to execute in reverse down to (but excluding) the specified migration
_MIGRATION="$2"


if [[ "${DEVELOPMENT}" == "True" ]]; then
    export DJANGO_READ_DOT_ENV_FILE=True
fi

python3 ./manage.py migrate_schemas ${_APP} ${_MIGRATION}

exit $?
