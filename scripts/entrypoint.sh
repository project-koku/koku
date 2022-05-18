#!/bin/bash

set -e
cd $APP_HOME
gunicorn koku.wsgi --access-logfile '-' --error-logfile '-' --config gunicorn_conf.py --preload
