#!/bin/bash
SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"

echo "Running Smoke Tests"

$SCRIPTPATH/run_test.sh 'iqe tests plugin hccm -k test_api -m hccm_smoke'
