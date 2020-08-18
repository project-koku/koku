#!/usr/bin/env python3
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
"""
Search for the koku SOURCE_REPOSITORY_REF setting in the
e2e-deploy buildfactory dir koku.yaml file.
"""
import os
import re
import sys

# This regex will search the yaml text for the following pattern:
#
# name: SOURCE_REPOSITORY_REF
# required: false
# value: XXXX
#
# To be able to replace XXXX with the correct ref
# reading the yaml and dumping the updated yaml was not used
# so that the whole file would not be reordered
regex = "^(.*?name: SOURCE_REPOSITORY_REF.*?" + os.linesep + ".*?required: false.*?" + os.linesep + ".*?value: )(.+?)$"

SRR = re.compile(regex, flags=re.MULTILINE)

TARGET_FILE = os.path.join(os.environ["E2E_REPO"], "buildfactory", "hccm", "koku.yaml")

try:
    GIT_REF = sys.argv[1]
except Exception:
    raise Exception(f"Usage: {os.path.basename(sys.argv[0])} <git-ref>")


# This is to ensure that the replacement has no issues since part of the grouping is multiline
def repl(match):
    return "{}{}".format(match.group(1), GIT_REF)


with open(TARGET_FILE, "rt+") as koku_yaml:
    buff = koku_yaml.read()
    koku_yaml.seek(0)
    koku_yaml.write(SRR.sub(repl, buff))
    koku_yaml.flush()
