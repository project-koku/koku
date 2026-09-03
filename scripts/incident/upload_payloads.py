#!/usr/bin/env python3
"""Upload ingress payload .tgz files to the team data warehouse bucket.

S3 keys follow the same prefix pattern as masu get_path_prefix() for processed CSV,
with an extra ingress-payload segment for raw archives (not daily CSV splits):

  data/csv/{schema}/OCP/ingress-payload/source={provider_uuid}/year=YYYY/month=MM/{request_id}.tgz

If provider_uuid is unknown, falls back to schema-level layout (no source= partition):

  data/csv/{schema}/OCP/ingress-payload/year=YYYY/month=MM/{request_id}.tgz

Requires AWS CLI credentials with s3:PutObject on the target bucket.

Usage:
    # 1) Test access (no uploads) — bucket name from internal runbook
    python upload_payloads.py check-access --bucket YOUR_BUCKET

    # 2) Dry-run keys
    python upload_payloads.py upload --bucket YOUR_BUCKET --schema org1234567 --dry-run

    # 3) Upload midnight subset
    python upload_payloads.py upload \\
        --bucket YOUR_BUCKET \\
        --schema org1234567 \\
        --manifest manifest-midnight-only.csv \\
        --input-dir payloads-midnight \\
        --provider-uuid-map cluster-provider-uuid.tsv

Provider map TSV (optional): cluster_id<TAB>provider_uuid
Generate via Gabi, e.g. join cluster/infrastructure id to api_provider.uuid for the tenant.
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = SCRIPT_DIR / "manifest.csv"
DEFAULT_INPUT_DIR = SCRIPT_DIR / "payloads"
DEFAULT_LOG = SCRIPT_DIR / "upload-log.csv"
WAREHOUSE_PATH = "data"
DATA_TYPE = "csv"
PROVIDER_TYPE = "OCP"
INGRESS_SEGMENT = "ingress-payload"

LOG_FIELDS = ["request_id", "status", "s3_key", "bytes", "error"]


def load_manifest(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_provider_uuid_map(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    mapping: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cluster_id, provider_uuid = line.split("\t", 1)
        mapping[cluster_id.strip()] = provider_uuid.strip()
    return mapping


def schema_from_org_id(org_id: str) -> str:
    org_id = org_id.strip()
    if org_id.startswith("org"):
        return org_id
    return f"org{org_id}"


def build_s3_key(
    schema: str,
    request_id: str,
    kafka_timestamp: str,
    cluster_id: str,
    provider_uuid_map: dict[str, str],
) -> str:
    ts = datetime.fromisoformat(kafka_timestamp.replace("Z", "+00:00"))
    year = ts.strftime("%Y")
    month = ts.strftime("%m")
    base = f"{WAREHOUSE_PATH}/{DATA_TYPE}/{schema}/{PROVIDER_TYPE}/{INGRESS_SEGMENT}"
    provider_uuid = provider_uuid_map.get(cluster_id, "")
    if provider_uuid:
        prefix = f"{base}/source={provider_uuid}/year={year}/month={month}"
    else:
        prefix = f"{base}/year={year}/month={month}"
    return f"{prefix}/{request_id}.tgz"


def run_aws(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["aws", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def cmd_check_access(bucket: str) -> int:
    identity = run_aws(["sts", "get-caller-identity"])
    if identity.returncode != 0:
        print("AWS credentials not configured or expired.", file=sys.stderr)
        print(identity.stderr.strip(), file=sys.stderr)
        print("\nTry: aws login  (or your team's rh-aws-saml-login flow)", file=sys.stderr)
        return 1

    print(identity.stdout.strip())
    listing = run_aws(["s3", "ls", f"s3://{bucket}/"])
    if listing.returncode != 0:
        print(f"Cannot list s3://{bucket}/", file=sys.stderr)
        print(listing.stderr.strip(), file=sys.stderr)
        return 1

    print(f"OK: list access on s3://{bucket}/")
    print(listing.stdout.strip() or "(bucket empty or no prefix output)")

    probe_key = f"{WAREHOUSE_PATH}/.ingress-upload-probe"
    probe_body = Path("/tmp/ingress-upload-probe.txt")
    probe_body.write_text("probe\n", encoding="utf-8")
    put = run_aws(["s3", "cp", str(probe_body), f"s3://{bucket}/{probe_key}"])
    if put.returncode != 0:
        print("List works but PutObject failed (read-only creds?).", file=sys.stderr)
        print(put.stderr.strip(), file=sys.stderr)
        return 1

    run_aws(["s3", "rm", f"s3://{bucket}/{probe_key}"])
    print("OK: write access confirmed (probe object uploaded and deleted)")
    return 0


def upload_one(local_path: Path, bucket: str, s3_key: str, dry_run: bool) -> dict:
    request_id = local_path.stem
    if dry_run:
        return {
            "request_id": request_id,
            "status": "dry-run",
            "s3_key": s3_key,
            "bytes": local_path.stat().st_size,
            "error": "",
        }

    result = run_aws(["s3", "cp", str(local_path), f"s3://{bucket}/{s3_key}"])
    if result.returncode != 0:
        return {
            "request_id": request_id,
            "status": "error",
            "s3_key": s3_key,
            "bytes": 0,
            "error": result.stderr.strip() or result.stdout.strip(),
        }
    return {
        "request_id": request_id,
        "status": "ok",
        "s3_key": s3_key,
        "bytes": local_path.stat().st_size,
        "error": "",
    }


def write_log(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=LOG_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def cmd_upload(args: argparse.Namespace) -> int:
    if not args.manifest.is_file():
        print(f"Manifest not found: {args.manifest}", file=sys.stderr)
        return 1
    if not args.input_dir.is_dir():
        print(f"Input dir not found: {args.input_dir}", file=sys.stderr)
        return 1

    schema = args.schema or schema_from_org_id(args.org_id or "")
    if not schema:
        print("Provide --schema or --org-id", file=sys.stderr)
        return 1

    provider_uuid_map = load_provider_uuid_map(args.provider_uuid_map)
    rows = load_manifest(args.manifest)
    results: list[dict] = []
    missing_local: list[str] = []

    for row in rows:
        request_id = row["request_id"]
        local_path = args.input_dir / f"{request_id}.tgz"
        if not local_path.is_file():
            missing_local.append(request_id)
            continue
        s3_key = build_s3_key(
            schema=schema,
            request_id=request_id,
            kafka_timestamp=row["kafka_timestamp"],
            cluster_id=row.get("cluster_id", ""),
            provider_uuid_map=provider_uuid_map,
        )
        result = upload_one(local_path, args.bucket, s3_key, args.dry_run)
        results.append(result)
        print(f"{result['status']:>7}  {request_id}  s3://{args.bucket}/{s3_key}")

    if missing_local:
        print(f"\nMissing local files: {len(missing_local)}", file=sys.stderr)

    if not args.dry_run:
        write_log(args.log, results)

    ok = sum(1 for r in results if r["status"] == "ok")
    errors = [r for r in results if r["status"] == "error"]
    print(f"\nDone: {ok}/{len(results)} uploaded, {len(errors)} errors, {len(missing_local)} missing local")
    if not provider_uuid_map:
        print(
            "Note: no --provider-uuid-map; used schema-level path (no source= partition). "
            "Add a map for full parity with daily CSV layout.",
            file=sys.stderr,
        )
    if args.dry_run:
        print("(dry-run — nothing uploaded)")
    return 1 if errors or missing_local else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check-access", help="Verify AWS CLI creds and bucket read/write")
    check.add_argument("--bucket", required=True)

    upload = sub.add_parser("upload", help="Upload .tgz files from manifest")
    upload.add_argument("--bucket", required=True)
    upload.add_argument("--schema", help="Tenant schema, e.g. org1234567")
    upload.add_argument("--org-id", help="Alternative to --schema (org prefix added if missing)")
    upload.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    upload.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    upload.add_argument("--provider-uuid-map", type=Path, help="TSV: cluster_id<TAB>provider_uuid")
    upload.add_argument("--log", type=Path, default=DEFAULT_LOG)
    upload.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if args.command == "check-access":
        return cmd_check_access(args.bucket)
    if args.command == "upload":
        return cmd_upload(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
