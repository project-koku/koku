#!/bin/bash

RESULT=$(scl enable rh-python38 "${APP_HOME}/manage.py check_migrations")

if [ "$RESULT" = "False" ]; then
    echo "Migration already executed."
else
    scl enable rh-python38 "${APP_HOME}/manage.py migrate_schemas --noinput"
fi
