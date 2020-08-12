#!/usr/bin/env python3
import argparse
import json
import sys
import urllib.request  # Using urllib because that's included in any python distro


parser = argparse.ArgumentParser()
parser.add_argument("--status-url", dest="status_url", metavar="URL", required=True, help="Application status URL")
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

resp = urllib.request.urlopen(args.status_url)
content = resp.read()
app_status = json.loads(content.decode("utf8"))
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
