#!/bin/bash
SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"
echo "Running Smoke Tests"

ENV_FOR_DYNACONF=local $SCRIPTPATH/run_test.sh 'iqe tests plugin --debug hccm -k test_api -m hccm_smoke'
