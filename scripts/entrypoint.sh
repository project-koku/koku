#!/bin/bash

set -e

echo $(id -u)

# enable container user without requiring nss_wrapper
if [ $(id -u) -ge 10000 ]; then
    echo "adding user $(id -u) to /etc/passwd"
    cat /etc/passwd | sed -e "s/^koku:/builder:/" > /tmp/passwd
    echo "koku:x:$(id -u):$(id -g):KokuUser:${HOME}:/bin/bash" >> /tmp/passwd
    cat /tmp/passwd > /etc/passwd
    rm /tmp/passwd
fi

if [[ -z "${ACG_CONFIG}" ]]; then
    CLOWDER_PORT=8000
else
    CLOWDER_PORT=$(python -c 'import app_common_python; print(app_common_python.LoadedConfig.publicPort)')
fi

cd $APP_HOME
gunicorn koku.wsgi --bind=0.0.0.0:$CLOWDER_PORT --access-logfile=- --config gunicorn_conf.py --preload
