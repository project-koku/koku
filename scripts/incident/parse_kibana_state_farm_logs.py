#!/usr/bin/env python3
"""Parse Kibana ES export and extract State Farm ingress payload URLs.

Input:  state-farm-downloading-payload-raw.json (Kibana Dev Tools export)
Output: manifest.csv (all unique request_ids)
        manifest-midnight-only.csv (size >= 100KB, kafka timestamp 00:00-02:00 UTC)
        urls.tsv (request_id<TAB>url) for batch curl inside the cluster

Usage:
    python parse_kibana_state_farm_logs.py
    python parse_kibana_state_farm_logs.py --input /path/to/export.json --output-dir ./out
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import re
import sys
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from urllib.parse import parse_qs
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = SCRIPT_DIR / "state-farm-downloading-payload-raw.json"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR

HIT_BLOCK_RE = re.compile(
    r'"@message"\s*:\s*"""(.*?)"""\s*,\s*\n\s*"@timestamp"\s*:\s*"([^"]+)"'
    r'(?:\s*,\s*\n\s*"@log_stream"\s*:\s*"([^"]*)")?',
    re.DOTALL,
)
MSG_PREFIX = "Downloading Payload for msg: "

REQUEST_ID_RE = re.compile(r"'request_id': '([^']+)'")
URL_RE = re.compile(r"'url': '(https://[^']+)'")
SIZE_RE = re.compile(r"'size': (\d+)")
KAFKA_TS_RE = re.compile(r"'timestamp': '([^']+)'")
ACCOUNT_RE = re.compile(r"'account': '([^']*)'")
ORG_ID_RE = re.compile(r"'org_id': '([^']+)'")
B64_IDENTITY_RE = re.compile(r"'b64_identity': '([^']+)'")
MIDNIGHT_MIN_SIZE_BYTES = 100_000
MIDNIGHT_HOUR_START = 0
MIDNIGHT_HOUR_END = 2  # exclusive upper bound: 00:00 <= t < 02:00 UTC


def load_hits_from_export(path: Path) -> list[dict]:
    """Extract hit fields from Kibana export (not strict JSON)."""
    text = path.read_text(encoding="utf-8")
    hits = []
    for match in HIT_BLOCK_RE.finditer(text):
        message, log_timestamp, log_stream = match.group(1), match.group(2), match.group(3) or ""
        hits.append(
            {
                "@message": message,
                "@timestamp": log_timestamp,
                "@log_stream": log_stream,
            }
        )
    if not hits:
        raise ValueError(f"No log hits found in {path} — check export format")
    return hits


def _regex_field(pattern: re.Pattern[str], message: str, name: str) -> str:
    match = pattern.search(message)
    if not match:
        raise ValueError(f"missing {name}")
    return match.group(1)


def _extract_kafka_fields(message: str) -> dict:
    return {
        "request_id": _regex_field(REQUEST_ID_RE, message, "request_id"),
        "url": _regex_field(URL_RE, message, "url"),
        "size": int(_regex_field(SIZE_RE, message, "size")),
        "timestamp": _regex_field(KAFKA_TS_RE, message, "timestamp"),
        "account": _regex_field(ACCOUNT_RE, message, "account"),
        "org_id": _regex_field(ORG_ID_RE, message, "org_id"),
        "b64_identity": (B64_IDENTITY_RE.search(message) or [None, ""])[1],
    }


def _cluster_id_from_identity(b64_identity: str) -> str:
    if not b64_identity:
        return ""
    try:
        padding = "=" * (-len(b64_identity) % 4)
        payload = json.loads(base64.b64decode(b64_identity + padding))
    except (json.JSONDecodeError, ValueError):
        return ""
    identity = payload.get("identity", {})
    system = identity.get("system", {}) or {}
    return system.get("cluster_id", "") or ""


def _url_expiry_utc(url: str) -> datetime | None:
    query = parse_qs(urlparse(url).query)
    amz_date = (query.get("X-Amz-Date") or [None])[0]
    expires = (query.get("X-Amz-Expires") or ["86400"])[0]
    if not amz_date:
        return None
    signed_at = datetime.strptime(amz_date, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    return signed_at + timedelta(seconds=int(expires))


def parse_hit(hit: dict) -> dict:
    source = hit if "@message" in hit else hit.get("_source", hit)
    message = source["@message"]
    if MSG_PREFIX not in message:
        raise ValueError("missing Downloading Payload prefix")
    kafka = _extract_kafka_fields(message)
    url = kafka["url"]
    b64_identity = kafka.get("b64_identity", "")
    expiry = _url_expiry_utc(url)
    return {
        "request_id": kafka["request_id"],
        "account": kafka.get("account", ""),
        "org_id": kafka.get("org_id", ""),
        "size": int(kafka["size"]),
        "url": url,
        "kafka_timestamp": kafka["timestamp"],
        "log_timestamp": source.get("@timestamp", ""),
        "log_stream": source.get("@log_stream", ""),
        "cluster_id": _cluster_id_from_identity(b64_identity),
        "x_amz_date": (parse_qs(urlparse(url).query).get("X-Amz-Date") or [""])[0],
        "url_expires_utc": expiry.isoformat() if expiry else "",
    }


def is_midnight_payload(row: dict) -> bool:
    if row["size"] < MIDNIGHT_MIN_SIZE_BYTES:
        return False
    try:
        ts = datetime.fromisoformat(row["kafka_timestamp"].replace("Z", "+00:00"))
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts = ts.astimezone(timezone.utc)
    return MIDNIGHT_HOUR_START <= ts.hour < MIDNIGHT_HOUR_END


def dedupe_rows(rows: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for row in rows:
        existing = by_id.get(row["request_id"])
        if existing is None or row["log_timestamp"] > existing["log_timestamp"]:
            by_id[row["request_id"]] = row
    return sorted(by_id.values(), key=lambda r: (r["kafka_timestamp"], r["request_id"]))


def write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "request_id",
        "kafka_timestamp",
        "log_timestamp",
        "size",
        "url",
        "url_expires_utc",
        "x_amz_date",
        "cluster_id",
        "account",
        "org_id",
        "log_stream",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_urls_tsv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(f"{row['request_id']}\t{row['url']}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--midnight-only",
        action="store_true",
        help="Only write midnight-filtered outputs (default: write both manifests)",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)

    raw_hits = load_hits_from_export(args.input)
    parsed = []
    errors = 0
    for hit in raw_hits:
        try:
            parsed.append(parse_hit(hit))
        except (ValueError, SyntaxError, KeyError) as exc:
            errors += 1
            print(f"WARN: skip hit: {exc}", file=sys.stderr)

    rows = dedupe_rows(parsed)
    midnight_rows = [r for r in rows if is_midnight_payload(r)]

    manifest_path = args.output_dir / "manifest.csv"
    midnight_path = args.output_dir / "manifest-midnight-only.csv"
    urls_path = args.output_dir / "urls.tsv"
    midnight_urls_path = args.output_dir / "urls-midnight-only.tsv"

    if args.midnight_only:
        write_csv(midnight_path, midnight_rows)
        write_urls_tsv(midnight_urls_path, midnight_rows)
    else:
        write_csv(manifest_path, rows)
        write_csv(midnight_path, midnight_rows)
        write_urls_tsv(urls_path, rows)
        write_urls_tsv(midnight_urls_path, midnight_rows)

    print(f"Parsed hits:     {len(raw_hits)}")
    print(f"Parse errors:    {errors}")
    print(f"Unique payloads: {len(rows)}")
    print(f"Midnight filter: {len(midnight_rows)} (size>={MIDNIGHT_MIN_SIZE_BYTES}, 00:00-02:00 UTC)")
    if not args.midnight_only:
        print(f"Wrote: {manifest_path}")
        print(f"Wrote: {urls_path}")
    print(f"Wrote: {midnight_path}")
    print(f"Wrote: {midnight_urls_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
