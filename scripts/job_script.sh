#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEV_SCRIPT_DIR=${SCRIPT_DIR%/*}/dev/scripts

${SCRIPT_DIR}/truncate_old_tables.py
