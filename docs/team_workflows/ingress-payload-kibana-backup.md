# Ingress payload backup via Kibana Dev Tools

Operational guide for preserving OCP ingress `.tgz` archives when the ingress listener
processing is slow, wedged, or at risk of losing data from ingress quarantine (~24h).

**Related:** ingress dead-letter queue (Unleash flag) — forward path for problematic tenants; see COST-8164.

**Prod-specific names** (Kibana URL, log index pattern, listener log stream, bucket names):
use the internal [service-docs runbook](https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/docs/operations/runbook.md) — do not copy them into public git.

---

## When to use this

- Listener pods are wedged or lagging on Kafka consume
- You need presigned ingress URLs before they expire (`X-Amz-Expires=86400`)
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
| Prod Kibana URL | service-docs runbook — Kibana section |
| Log index pattern | Cost Management CloudWatch/Kibana index for your environment |
| Log stream filter | Ingress listener deployment name in that namespace |
| Target log line | `Downloading Payload for msg: {...}` |
| Log source code | `koku/masu/external/kafka_msg_handler.py` |

Use **Dev Tools** (not Discover CSV export) for full `_search` responses with `@message` bodies.

Open: **Menu → Dev Tools → Console**

---

## Dev Tools query

Replace placeholders with values from your **internal incident notes** (do not paste real tenant IDs into public git):

- `LOG_INDEX` — Kibana index pattern from internal runbook (e.g. daily `*-YYYY.MM.DD` indices)
- `ORG_ID` — numeric org id from Kafka payload / customer record
- `ACCOUNT_ID` — RH account number (optional extra filter)
- `@timestamp` range — incident window in UTC

```http
GET LOG_INDEX/_search
{
  "size": 500,
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
            "query": "\"Downloading Payload\" AND (ORG_ID OR ACCOUNT_ID)",
            "default_field": "@message"
          }
        }
      ]
    }
  },
  "_source": ["@timestamp", "@message", "@log_stream"]
}
```

Substitute `LOG_INDEX` with the real index pattern from internal docs before running.

### Pagination

If `hits.total` exceeds 500, repeat with `search_after` using the last hit's `sort` values until `hits.hits` is empty.

### Save export

1. Run the query in Dev Tools
2. Copy the full JSON response (or use Kibana export if available in your environment)
3. Save locally as `scripts/incident/kibana-downloading-payload-export.json` (local only — see README)

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

---

## Local pipeline

Scripts live in [`scripts/incident/`](../../scripts/incident/). See [`scripts/incident/README.md`](../../scripts/incident/README.md).

```bash
cd scripts/incident

# Parse export → manifest.csv, manifest-midnight-only.csv, urls.tsv
python3 parse_kibana_ingress_payload_logs.py

# Download .tgz archives (run while URLs are valid)
python3 download_payloads.py --skip-existing

# Optional: copy midnight subset to payloads-midnight/
python3 split_midnight_payloads.py
```

### Midnight payload heuristic

For full-day OCP reports (not small metadata uploads):

1. `size >= 100_000` (100 KB)
2. Kafka `timestamp` in UTC window `00:00`–`02:00`

Validate counts with your team lead if the filter looks wrong.

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

- [service-docs runbook — Kibana](https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/docs/operations/runbook.md)
- Listener message handler: `koku/masu/external/kafka_msg_handler.py`
