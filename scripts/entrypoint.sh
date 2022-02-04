#!/bin/bash

set -e
cd $APP_HOME
gunicorn koku.wsgi --access-logfile=- --config gunicorn_conf.py --preload
