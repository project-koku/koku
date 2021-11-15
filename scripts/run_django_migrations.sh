#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# The "scripts" dir should be a sibling to the "koku" dir that actually contains the app code
cd ../koku

# Leave _APP and _MIGRATION unset to execute any migrations for all apps
# Put a registered app name here to constrain migrations to that app only
_APP=
# Put a migration number (or full name minus the '.py')
# to execute up to (and including) the specified migration
# or to execute in reverse down to (but excluding) the specified migration
_MIGRATION=

DJANGO_READ_DOT_ENV_FILE=True python3 ./manage.py migrate_schemas $(_APP) $(_MIGRATION)

exit $?
