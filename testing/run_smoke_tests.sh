#!/bin/bash
echo "Running Smoke Tests"

./run_test.sh 'iqe tests plugin hccm -k test_api -m hccm_smoke'
