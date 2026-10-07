# Ingress payload backup via Kibana Dev Tools

Operational guide for preserving OCP ingress `.tgz` archives when the ingress listener
processing is slow, wedged, or at risk of losing data from ingress quarantine (~24h).

**Related:** ingress dead-letter queue (Unleash flag) — forward path for problematic tenants; see COST-8164.

**Prod-specific names** (Kibana URL, log index pattern, listener log stream, bucket names):
use the internal [service-docs runbook](https://gitlab.cee.redhat.com/cost-management/service-docs/-/blob/main/docs/operations/runbook.md) — do not copy them into public git.

**CLI triage (≤1000 hits):** internal
[`scripts/kibana-search`](https://gitlab.cee.redhat.com/cost-management/service-docs/-/blob/main/scripts/kibana-search)
and [Kibana log search](https://gitlab.cee.redhat.com/cost-management/service-docs/-/blob/main/docs/operations/kibana-log-search.md)
(authenticated browser cURL). That helper does **not** paginate large exports; for
multi-thousand-hit incident dumps use Dev Tools + `search_after` below (or extend the CLI).

---

## When to use this

- Listener pods are wedged or lagging on Kafka consume
- You need presigned ingress URLs before they expire (`X-Amz-Expires=86400`)
- URLs are **already expired** and you need a **key list** (`request_id` + `X-Amz-Date`)
  so someone with ingress S3 access can recover objects before quarantine lifecycle delete
- `oc logs` on listener pods does not go back far enough (short retention)

## What this covers

Messages where the listener **already logged** `Downloading Payload for msg:` in the cost-management Kibana log index.

## What this does **not** cover

| Gap | Why | What to do instead |
|-----|-----|-------------------|
| Kafka backlog not yet consumed | No `Downloading Payload` log line; URL never surfaced in Kibana | Read/consume prod Kafka topic (AppSRE access) or enable DLQ flag per schema |
| Payloads after your Kibana export window | Export is a point-in-time snapshot | Re-run query with extended `@timestamp` range |
| Long-term reingest | Backup is raw archive storage | Coordinate with pipeline owners (DLQ table + S3 prefix) |

---

## Kibana setup

| Item | Where to find it |
|------|------------------|
| Prod Kibana URL | [service-docs runbook — Kibana](https://gitlab.cee.redhat.com/cost-management/service-docs/-/blob/main/docs/operations/runbook.md#kibana) |
| Log index pattern | Cost Management CloudWatch/Kibana index for your environment |
| Log stream filter | Ingress listener deployment name in that namespace |
| Target log line | `Downloading Payload for msg: {...}` |
| Log source code | `koku/masu/external/kafka_msg_handler.py` |

Use **Dev Tools** (not Discover CSV export) for full `_search` responses with `@message` bodies.

Open: **Menu → Dev Tools → Console**

Do **not** put the listener deployment name in the `@message` `query_string` — that value
usually lives in `@log_stream`, so AND-ing it into `@message` returns zero hits.

---

## Dev Tools query

Replace placeholders with values from your **internal incident notes** (do not paste real tenant IDs into public git):

- `LOG_INDEX` — Kibana index pattern from internal runbook (e.g. daily `*-YYYY.MM.DD` indices)
- `ORG_ID` — numeric org id from Kafka payload / customer record (optional; omit for platform-wide incidents)
- `ACCOUNT_ID` — RH account number (optional extra filter)
- `@timestamp` range — incident window in UTC; use a **fixed** `lte` while paginating (not `now`)

Platform-wide (no tenant filter):

```http
GET LOG_INDEX/_search
{
  "size": 5000,
  "sort": [{ "@timestamp": "asc" }, { "_id": "asc" }],
  "query": {
    "bool": {
      "filter": [
        {
          "range": {
            "@timestamp": {
              "gte": "2026-01-01T00:00:00Z",
              "lte": "2026-01-02T23:59:59Z"
            }
          }
        }
      ],
      "must": [
        {
          "query_string": {
            "query": "\"Downloading Payload\"",
            "default_field": "@message"
          }
        }
      ]
    }
  },
  "_source": ["@timestamp", "@message", "@log_stream"]
}
```

Single-tenant variant: add `AND (ORG_ID OR ACCOUNT_ID)` inside the `query_string` if needed.

Substitute `LOG_INDEX` with the real index pattern from internal docs before running.
If `size: 5000` is rejected by the cluster, fall back to `500`.

### Pagination

If a page returns a full `size` of hits, repeat with `search_after` using the **last** hit's
`sort` values until a page returns fewer than `size` hits (or an empty `hits` array).

`hits.total` is the **entire** match count for the query — it is **not** “remaining pages.”
As listeners recover, new log lines can increase `hits.total`; a fixed `lte` keeps the export stable.

### Save export

1. Run the query in Dev Tools
2. Save each page JSON response body to disk (outside Git)
3. Point the parser at the export(s) with `--input` / a directory of pages (local only — see README)

The parser accepts standard `_search` JSON (`hits.hits[]._source`). Kibana console exports
that use triple-quoted `@message` values are also supported.

---

## Fields in `@message`

The listener logs a Python dict string. Extract:

| Field | Use |
|-------|-----|
| `request_id` | Archive filename / dedupe key |
| `url` | Presigned URL for the ingress quarantine object |
| `size` | Bytes; filter large payloads (midnight heuristic) |
| `timestamp` | Kafka message timestamp (use for midnight window) |
| `org_id` / `account` | Tenant filters |
| `b64_identity` | Decode for OpenShift `cluster_id` |

Presigned URLs expire **24 hours** after `X-Amz-Date`. Prioritize oldest `X-Amz-Date` first.
The object key in the ingress quarantine bucket is the `request_id`.

Do not confuse columns:

| Field | Meaning |
|-------|---------|
| `X-Amz-Date` / kafka `timestamp` | When the URL was signed / message produced |
| `url_expires_utc` | `X-Amz-Date` + 24h (link death) |
| Log `@timestamp` | When the listener logged `Downloading Payload` (often much later during recovery) |

---

## Local pipeline

Scripts live in [`scripts/incident/`](../../scripts/incident/). See [`scripts/incident/README.md`](../../scripts/incident/README.md).

```bash
cd scripts/incident

# Parse export → manifest.csv, manifest-midnight-only.csv, urls.tsv
python3 parse_kibana_ingress_payload_logs.py

# Download .tgz archives (ONLY while URLs are still valid)
python3 download_payloads.py --skip-existing

# Optional: copy midnight subset to payloads-midnight/
python3 split_midnight_payloads.py
```

### What the parser produces vs what download can do

| Output | Meaning |
|--------|---------|
| Full `manifest.csv` | Every unique `request_id` seen in `Downloading Payload` logs for the export window |
| Expired URLs | Presigned link past TTL — **HTTP download script cannot fetch these** |
| Still-valid URLs | `download_payloads.py` can GET them unauthenticated (signature is in the URL) |
| Midnight heuristic CSV | Candidate full-day reports (see below) — validate with the team |

Expired keys still matter: share `request_id` + `X-Amz-Date` with whoever has ingress S3
CLI access so objects can be pulled from quarantine before lifecycle delete. Re-run the
Kibana export after listeners stabilize (and once more later) so the list stays current.

Importing the full manifest into a shared spreadsheet (with flags for expired / midnight)
is useful for team review; keep spreadsheets and CSVs **out of git**.

### Midnight payload heuristic

For full-day OCP reports (not small metadata uploads). Operator upload timing is treated as
**UTC** unless the team learns otherwise:

1. `size >= 100_000` (100 KB)
2. Kafka `timestamp` in UTC window `00:00`–`02:00`

Validate counts with your team lead if the filter looks wrong. Finer filtering (full calendar
day inside the tarball manifest) is a **second** step after archives are on disk.

---

## Upload to team S3

Use the **data warehouse bucket** and namespace credentials documented internally for your environment.

**Suggested prefix** (confirm with team lead):

```text
data/csv/org{ORG_ID}/OCP/ingress-payload/year=YYYY/month=MM/{request_id}.tgz
```

Human SSO roles are often **read-only** on the warehouse bucket. Options:

1. Temporary `PutObject` grant via AppSRE (incident access request)
2. Upload from a cost-management prod pod with Clowder S3 credentials (`oc cp` + `aws s3 cp` inside pod)
3. `upload_payloads.py` when your CLI has write access (pass `--bucket` from internal docs):

```bash
python3 upload_payloads.py check-access --bucket YOUR_BUCKET
python3 upload_payloads.py upload --bucket YOUR_BUCKET --dry-run
# Optional: restrict to one tenant when manifest might span orgs
python3 upload_payloads.py upload --bucket YOUR_BUCKET --schema org1234567 --dry-run
```

---

## Security

**Never commit to koku upstream:**

- Kibana exports, `manifest.csv`, `urls.tsv` (contain presigned URLs)
- Downloaded `.tgz` payloads (customer data)
- Customer names, real org/account IDs, prod bucket/index names in docs or filenames

Use test placeholders (`org1234567`, account `10001`) in examples only.

---

## See also

- [service-docs runbook — Kibana](https://gitlab.cee.redhat.com/cost-management/service-docs/-/blob/main/docs/operations/runbook.md#kibana)
- [service-docs — Kibana log search / `kibana-search` CLI](https://gitlab.cee.redhat.com/cost-management/service-docs/-/blob/main/docs/operations/kibana-log-search.md)
- Listener message handler: `koku/masu/external/kafka_msg_handler.py`
