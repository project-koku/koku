#!/bin/bash

set -e

if [[ -z "${ACG_CONFIG}" ]]; then
    CLOWDER_PORT=8000
else
    CLOWDER_PORT=$(python -c 'import app_common_python; print(app_common_python.LoadedConfig.publicPort)')
fi

cd $APP_HOME
gunicorn koku.wsgi --bind=0.0.0.0:$CLOWDER_PORT --access-logfile=- --config gunicorn_conf.py --preload
