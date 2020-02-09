#!/bin/bash

APP_NAME_DEFAULT="koku"
APP_NAME="${1:-$APP_NAME_DEFAULT}"
APP_PORT="${KOKU_SERVICE_PORT:-'8080'}"
TARGET_DEFAULT="http://${APP_NAME}.${APP_NAMESPACE}.svc.cluster.local:${APP_PORT}"
TARGET="${2:-$TARGET_DEFAULT}"
COMMIT=`curl  -X GET ${TARGET}${API_PATH_PREFIX}/v1/status/ | sed 's/{.*commit":"*\([0-9a-zA-Z]*\)"*,*.*}/\1/'`

echo "COMMIT=$COMMIT"
echo "OPENSHIFT_BUILD_COMMIT=$OPENSHIFT_BUILD_COMMIT"

if [ "$COMMIT" = "$OPENSHIFT_BUILD_COMMIT" ]; then
    echo "Migration already executed."
else
    scl enable rh-python36 "${APP_HOME}/manage.py migrate_schemas --noinput"
fi
