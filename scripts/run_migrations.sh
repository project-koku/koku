#!/bin/bash

RESULT=$(scl enable rh-python38 "${APP_HOME}/manage.py check_migrations | tail -1")

if [ "$RESULT" = "True" ]; then
    echo "Migration already executed."
else
    scl enable rh-python38 "${APP_HOME}/manage.py migrate_schemas --noinput"
fi
