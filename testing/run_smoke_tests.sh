#!/bin/bash
SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"
echo "Running Smoke Tests"

ENV_FOR_DYNACONF=local $SCRIPTPATH/run_test.sh 'iqe tests plugin cost_management -k test_api -m cost_smoke --pdb'
