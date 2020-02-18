#!/usr/bin/python
#
# Copyright 2018 Red Hat, Inc.
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
"""RDS Exporter config file deployer."""
import json
import os
import sys

import yaml

APP_ROOT = os.environ.get("APP_ROOT")
CONFIG = os.environ.get("RDS_EXPORTER_CONFIG")

if APP_ROOT and CONFIG:
    FILENAME = f"{APP_ROOT}/etc/config.yml"
    with open(FILENAME, "w") as fh:
        yaml.safe_dump(json.loads(CONFIG), fh, default_flow_style=False)
else:
    print("Environment vars APP_ROOT and RDS_EXPORTER_CONFIG are required.")
    sys.exit(-1)
