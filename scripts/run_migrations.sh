#!/bin/bash

STATUS_PROBE="${APP_HOME}/../scripts/status_probe.py"
APP_NAME_DEFAULT="koku"
APP_NAME="${1:-$APP_NAME_DEFAULT}"
APP_PORT="${KOKU_SERVICE_PORT:-'8080'}"
TARGET_DEFAULT="http://${APP_NAME}.${APP_NAMESPACE}.svc.cluster.local:${APP_PORT}"
TARGET="${2:-$TARGET_DEFAULT}"
COMMIT=$(scl enable rh-python36 "${STATUS_PROBE} --status-url ${TARGET}${API_PATH_PREFIX}/v1/status/ --path commit")

echo "COMMIT=$COMMIT"
echo "OPENSHIFT_BUILD_COMMIT=$OPENSHIFT_BUILD_COMMIT"

if [ "$COMMIT" = "$OPENSHIFT_BUILD_COMMIT" ]; then
    echo "Migration already executed."
else
    scl enable rh-python36 "${APP_HOME}/manage.py migrate_schemas --noinput"
fi
