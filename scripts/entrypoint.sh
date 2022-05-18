#!/bin/bash

set -e
cd $APP_HOME
gunicorn koku.wsgi --config gunicorn_conf.py --preload
