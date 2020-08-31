#!/usr/bin/env python3
#
# Copyright 2020 Red Hat, Inc.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
import argparse
import json
import sys

import requests


parser = argparse.ArgumentParser()
parser.add_argument("--status-url", dest="status_url", metavar="URL", required=False, help="Application status URL")
parser.add_argument(
    "--file", dest="filename", metavar="FILE", required=False, help='File to read (use "-" for stdin)', default="-"
)
parser.add_argument(
    "--path",
    dest="path",
    metavar="PATH",
    required=True,
    help="Path of keys to get a value from the returned JSON content",
)
parser.add_argument(
    "--display-key", dest="display_key", action="store_true", default=False, help="Display key with value"
)
args = parser.parse_args()

if args.status_url:
    resp = requests.get(args.status_url)
    if resp.status_code != 200:
        raise Exception(f"Server did not responde with 200! ({resp.status_code})")

    app_status = resp.json()
else:
    if args.filename == "-":
        jfile = sys.stdin
    else:
        jfile = open(args.filename, "rt")

    content = jfile.read()
    if jfile != sys.stdin:
        jfile.close()
    app_status = json.loads(content)


paths = args.path.split(";")

for path in paths:
    value = app_status
    if args.display_key:
        print(f"{path}\t", end="")
    for key in path.split("."):
        if key.isdigit():
            key = int(key)
        value = value[key]
    print(value)

sys.stdout.flush()

sys.exit(0)
