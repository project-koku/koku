#!/usr/bin/env python3
"""Download ingress payload archives from manifest.csv or urls.tsv.

Input:  manifest.csv (or urls.tsv / urls-midnight-only.tsv)
Output: payloads/{request_id}.tgz, download-log.csv

Usage:
    python download_payloads.py
    python download_payloads.py --manifest manifest-midnight-only.csv --output-dir payloads-midnight
    python download_payloads.py --workers 5 --skip-existing
"""
from __future__ import annotations

import argparse
import csv
import sys
import urllib.error
import urllib.request
from concurrent.futures import as_completed
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = SCRIPT_DIR / "manifest.csv"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "payloads"
DEFAULT_LOG = SCRIPT_DIR / "download-log.csv"

LOG_FIELDS = ["request_id", "status", "bytes", "error"]


def load_rows(path: Path) -> list[dict]:
    if path.suffix == ".tsv" or path.name.startswith("urls"):
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            request_id, url = line.split("\t", 1)
            rows.append({"request_id": request_id, "url": url})
        return rows

    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def download_one(request_id: str, url: str, output_dir: Path, skip_existing: bool) -> dict:
    out_path = output_dir / f"{request_id}.tgz"
    if skip_existing and out_path.is_file() and out_path.stat().st_size > 0:
        return {
            "request_id": request_id,
            "status": "skipped",
            "bytes": out_path.stat().st_size,
            "error": "",
        }

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "koku-incident-backup/1.0"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = resp.read()
        out_path.write_bytes(data)
        return {"request_id": request_id, "status": "ok", "bytes": len(data), "error": ""}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"request_id": request_id, "status": "error", "bytes": 0, "error": str(exc)}


def write_log(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=LOG_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()

    if not args.manifest.is_file():
        print(f"Manifest not found: {args.manifest}", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = load_rows(args.manifest)
    if not rows:
        print("No rows to download", file=sys.stderr)
        return 1

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(
                download_one,
                row["request_id"],
                row["url"],
                args.output_dir,
                args.skip_existing,
            ): row["request_id"]
            for row in rows
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(f"{result['status']:>7}  {result['request_id']}  {result['bytes']}")

    results.sort(key=lambda r: r["request_id"])
    write_log(args.log, results)

    ok = sum(1 for r in results if r["status"] in ("ok", "skipped"))
    errors = [r for r in results if r["status"] == "error"]
    print(f"\nDone: {ok}/{len(results)} ok/skipped, {len(errors)} errors")
    print(f"Wrote: {args.log}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
