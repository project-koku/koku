#!/usr/bin/python
#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""RDS Exporter config file deployer."""
import json
import os
import sys

import yaml

APP_ROOT = os.environ.get("APP_ROOT")
CONFIG = os.environ.get("RDS_EXPORTER_CONFIG")

if APP_ROOT and CONFIG:
    FILENAME = os.path.join(APP_ROOT, "etc", "config.yml")
    with open(FILENAME, "w") as fh:
        yaml.safe_dump(json.loads(CONFIG), fh, default_flow_style=False)
else:
    print("Environment vars APP_ROOT and RDS_EXPORTER_CONFIG are required.")
    sys.exit(-1)
