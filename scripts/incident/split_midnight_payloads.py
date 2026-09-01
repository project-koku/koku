#!/usr/bin/env python3
"""Copy midnight-filtered payloads into a separate directory.

Reads request_ids from manifest-midnight-only.csv and copies matching
{request_id}.tgz files from payloads/ to payloads-midnight/.

Usage:
    python split_midnight_payloads.py
    python split_midnight_payloads.py --source payloads --dest payloads-midnight
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = SCRIPT_DIR / "manifest-midnight-only.csv"
DEFAULT_SOURCE = SCRIPT_DIR / "payloads"
DEFAULT_DEST = SCRIPT_DIR / "payloads-midnight"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--symlink", action="store_true", help="Use symlinks instead of copies")
    args = parser.parse_args()

    if not args.manifest.is_file():
        print(f"Manifest not found: {args.manifest}", file=sys.stderr)
        return 1
    if not args.source.is_dir():
        print(f"Source dir not found: {args.source}", file=sys.stderr)
        return 1

    args.dest.mkdir(parents=True, exist_ok=True)

    with args.manifest.open(encoding="utf-8") as fh:
        request_ids = [row["request_id"] for row in csv.DictReader(fh)]

    copied = 0
    missing = []
    for request_id in request_ids:
        src = args.source / f"{request_id}.tgz"
        dst = args.dest / f"{request_id}.tgz"
        if not src.is_file():
            missing.append(request_id)
            continue
        if args.symlink:
            if dst.is_symlink() or dst.exists():
                dst.unlink()
            dst.symlink_to(src.resolve())
        else:
            shutil.copy2(src, dst)
        copied += 1

    print(f"Midnight payloads: {len(request_ids)} in manifest")
    print(f"Copied:            {copied} -> {args.dest}")
    if missing:
        print(f"Missing:           {len(missing)}", file=sys.stderr)
        for request_id in missing:
            print(f"  - {request_id}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
