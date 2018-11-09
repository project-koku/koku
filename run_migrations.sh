#!/bin/bash
sleep 15
python koku/manage.py migrate_schemas --database $DATABASE_HOST:$DATABASE_PORT