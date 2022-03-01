#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
${SCRIPT_DIR}/cji_scripts/truncate_old_tables.py
