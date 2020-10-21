#!/bin/bash
#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
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
