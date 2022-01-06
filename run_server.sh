#!/bin/sh
sleep 5
python koku/manage.py migrate_schemas
if [[ -z "$RUN_GUNICORN" ]]; then
    DJANGO_READ_DOT_ENV_FILE=True python koku/manage.py runserver 0.0.0.0:8000
else
    cd ./koku
    PYTHONPATH="$(pwd):${PYTHONPATH}"
    DJANGO_READ_DOT_ENV_FILE=True gunicorn koku.wsgi --bind=0.0.0.0:8000 --access-logfile=- --error-logfile=- --config "gunicorn_conf.py"
fi
