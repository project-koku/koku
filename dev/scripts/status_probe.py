#!/usr/bin/env python3
#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import argparse
import json
import logging
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
parser.add_argument(
    "--no-convert-int-key",
    dest="convert_int",
    action="store_false",
    default=True,
    help="Do not convert digit keys to integers",
)
choices = ("INFO", "WARNING", "DEBUG", "ERROR")
parser.add_argument(
    "--log-level",
    dest="level",
    default="INFO",
    choices=choices,
    metavar="LEVEL",
    help=f"Set log level {choices}. Default: INFO",
)

args = parser.parse_args()
logging.basicConfig(
    format="%(asctime)s %(name)s [%(levelname)s] %(message)s", stream=sys.stderr, level=getattr(logging, args.level)
)
LOG = logging.getLogger("status_probe")

if args.status_url:  # noqa: C901
    LOG.debug(f"Reading status from {args.status_url}")
    resp = requests.get(args.status_url)
    if resp.status_code != 200:
        LOG.error(f"Server did not responde with 200! ({resp.status_code})")
        sys.exit(-2)

    app_status = resp.json()
else:
    if args.filename == "-":
        fname = "stdin"
        jfile = sys.stdin
    else:
        fname = args.filename
        try:
            jfile = open(args.filename, "rt")
        except (IOError, OSError) as e:
            LOG.error(f"{e.__class__.__name__}: Cannot open file {fname}: {e}")
            sys.exit(-1)

    LOG.debug(f"Reading status from {fname}")
    try:
        content = jfile.read()
    except (IOError, OSError) as e:
        LOG.error(f"{e.__class__.__name__}: Cannot read file {fname}: {e}")
        sys.exit(-1)

    if jfile != sys.stdin:
        jfile.close()

    if content:
        try:
            app_status = json.loads(content)
        except (IOError, OSError, json.JSONDecodeError) as e:
            LOG.error(f"{e.__class__.__name__}: Cannot parse json: {e}")
            sys.exit(-1)
    else:
        LOG.warning("No content to parse!")
        sys.exit(1)


paths = args.path.split(";")

for path in paths:
    LOG.debug(f'Processing path "{path}"')
    value = app_status
    err = False
    for key in path.split("."):
        if key.isdigit() and args.convert_int:
            key = int(key)

        LOG.debug(f'Processing "{key}" ({type(key).__name__}) from path "{path}"')
        try:
            value = value[key]
        except KeyError:
            LOG.error(f'Key "{key}" ({type(key).__name__}) in path "{path}" does not exist.')
            err = True

    if not err:
        if args.display_key:
            print(f"{path}\t", end="")
        print(value)

sys.stdout.flush()

sys.exit(0)
