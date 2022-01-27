#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

${SCRIPT_DIR}/copy_static_perspective_data.py

python3.8 scripts/migrate_presto.py --noinput
