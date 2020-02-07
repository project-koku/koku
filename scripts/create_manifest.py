#!/usr/bin/env python
#
# Copyright 2019 Red Hat, Inc.
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
import json

lockfile = {}


with open("Pipfile.lock") as json_file:
    lockfile = json.load(json_file)

with open("koku-manifest", "w") as manifest:
    for name, value in sorted(lockfile["default"].items()):
        if "version" in value:
            version = value["version"].replace("=", "")
            manifest.write(f"mgmt_services/cost-mgmt:koku/python-{name}:{version}.pipfile\n")
        elif "ref" in value:
            ref = value["ref"]
            manifest.write(f"mgmt_services/cost-mgmt:koku/python-{name}:{ref}.pipfile\n")
        else:
            raise "unable to parse %s" % value
