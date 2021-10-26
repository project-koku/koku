#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

${SCRIPT_DIR}/copy_static_aws_perspective_data.py
