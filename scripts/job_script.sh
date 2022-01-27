#! /usr/bin/env python3.8

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

${SCRIPT_DIR}/copy_static_perspective_data.py

${SCRIPT_DIR}/migrate_trino.py --noinput
