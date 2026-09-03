# Ingress payload incident scripts

Operational helpers to back up OCP ingress `.tgz` files when listener processing is delayed
or wedged. **Do not commit** generated manifests, exports, or payload archives.

Full runbook (Kibana Dev Tools queries, limitations, S3 upload):
[`docs/team_workflows/ingress-payload-kibana-backup.md`](../../docs/team_workflows/ingress-payload-kibana-backup.md)

Prod-specific values (Kibana index, buckets, namespaces): internal service-docs runbook only.

## Scripts

| Script | Purpose |
|--------|---------|
| `parse_kibana_ingress_payload_logs.py` | Parse Kibana Dev Tools export → `manifest.csv`, midnight filter, `urls.tsv` |
| `download_payloads.py` | Download `.tgz` from presigned URLs in manifest |
| `split_midnight_payloads.py` | Copy midnight-filtered payloads to `payloads-midnight/` |
| `upload_payloads.py` | Upload local `.tgz` via AWS CLI (`--bucket` required) |

## Local outputs (never commit)

The scripts write `manifest.csv`, `urls.tsv`, `payloads/`, and Kibana exports beside this
directory. Those files contain presigned URLs and customer data. `.gitignore` blocks
accidental `git add`; still review `git status` before every commit.

## Quick start

```bash
cd scripts/incident

# 1. Save Kibana Dev Tools export (see runbook) → kibana-downloading-payload-export.json
python3 parse_kibana_ingress_payload_logs.py

# 2. Download archives (before presigned URLs expire)
python3 download_payloads.py --skip-existing

# 3. Optional: isolate midnight payloads
python3 split_midnight_payloads.py

# 4. Upload (dry-run first; bucket from internal runbook)
python3 upload_payloads.py upload --bucket YOUR_BUCKET --schema org1234567 --dry-run
```

Replace `org1234567` with the tenant schema from your internal incident notes.
