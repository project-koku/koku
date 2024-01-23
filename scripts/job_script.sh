#!/bin/bash

# SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# CJI_SCRIPT_DIR="${SCRIPT_DIR}/cji_scripts"
# ${CJI_SCRIPT_DIR}/migrate_trino.py

python koku/manage.py aws_null_bill_cleanup --bill-date=2023-12-01
