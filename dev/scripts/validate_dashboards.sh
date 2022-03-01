#!/bin/bash
#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
trap handle_errors ERR

function handle_errors() {
    echo "Validation failed."
    exit 1
}

SCRIPT_DIR="$( pushd "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"
DASHBOARD_DIR="$SCRIPT_DIR/../dashboards"

OC=$(which oc)
JQ=$(which jq)

for dashboard in $(ls -1 $DASHBOARD_DIR/*.yaml); do
    echo "Checking $dashboard"
    $OC extract -f $dashboard --to=- | $JQ '.' > /dev/null
done

echo "Success. All files valid."
