#!/usr/bin/env python
#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import json

lockfile = {}

CONTAINER_NAME = "registry.access.redhat.com/ubi8/python-38:latest"

with open("Pipfile.lock") as json_file:
    lockfile = json.load(json_file)

with open("koku-manifest", "w") as manifest:
    manifest.write(f"mgmt_services/cost-mgmt:koku/{CONTAINER_NAME}\n")
    for name, value in sorted(lockfile["default"].items()):
        if "version" in value:
            version = value["version"].replace("=", "")
            manifest.write(f"mgmt_services/cost-mgmt:koku/python-{name}:{version}.pipfile\n")
        elif "ref" in value:
            ref = value["ref"]
            manifest.write(f"mgmt_services/cost-mgmt:koku/python-{name}:{ref}.pipfile\n")
        else:
            raise "unable to parse %s" % value
