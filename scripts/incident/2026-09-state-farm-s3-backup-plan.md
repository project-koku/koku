# Plan: State Farm S3 backup via Kibana logs

**Incident:** `koku-clowder-listener` pods wedged — OCP ingest blocked
**Customer:** State Farm — `org16594026` / account `11439097`
**Owners:** Lucas Bacciotti + Victor Sizilio
**Plan date:** 2026-09-01
**Status:** 262/262 payloads downloaded locally; scripts in repo; S3 upload pending

---

## What we already know (Dev Tools)

| Item | Value |
|------|-------|
| Correct index | `cwl-hccm-prod-YYYY.MM.DD` (e.g. `cwl-hccm-prod-2026.08.31`) |
| Primary field | `@message` (string; embedded Python dict) |
| Log group / stream | `@log_group`: `hccm-prod`; `@log_stream`: `koku-clowder-listener-*` |
| Target line | `Downloading Payload for msg: {...}` |
| Org filter | `"org_id': '16594026'"` or `11439097` in `@message` |
| Total in incident window | **263 hits** (`2026-08-31T22:00:00Z` → `2026-09-01T23:59:59Z`) |
| Incident start (1st SF) | `2026-08-31T22:00:01Z` — `request_id` `5d6d808644034498acee1784418b8778` |
| Source bucket | `insights-ingress-prod` (presigned URL in log) |
| URL expiry | `X-Amz-Expires=86400` → **24h** after `X-Amz-Date` |
| `oc logs` (72h) | ~34 lines — **insufficient**; Kibana is the source of truth |

**Fields to extract from `@message`:**

- `request_id` (= `tracing_id`)
- `url` (presigned S3)
- `size` (bytes)
- `timestamp` (Kafka / ingress timestamp)
- `b64_identity` → `cluster_id` (to group by OpenShift cluster)

---

## Backup goal

Save **ingress tar.gz** files before they leave quarantine (~24h), for future reprocessing (new Kafka path — Cody/David).

**Team-agreed scope:** focus on **midnight payload** (full-day report), not every incremental upload.

---

## Criterion: what is a “midnight payload”

Initial heuristic (validate with Luke if the count looks wrong):

1. **`size >= 100_000`** (100 KB) — excludes metadata ~1.5–5 KB
2. **UTC window `00:00–02:00`** on the Kafka payload `timestamp` (not just log `@timestamp`)
3. Optional: **one payload per `cluster_id` per day** — largest `size` in the window

Priority days:

| Day (UTC) | ES index | Note |
|-----------|----------|------|
| 2026-08-31 | `cwl-hccm-prod-2026.08.31` | Incident start ~22:00; midnight batch ~00:00 on the 1st |
| 2026-09-01 | `cwl-hccm-prod-2026.09.01` | Continuation + midnight for the 1st |

---

## URGENCY: URL expiration

| `X-Amz-Date` | Approx. expiry |
|--------------|----------------|
| `20260831T22*` | ~2026-09-01 22:00 UTC |
| `20260901T00*` | ~2026-09-02 00:00 UTC |
| `20260901T12*` | ~2026-09-02 12:00 UTC |

**Action:** download **today** everything with `X-Amz-Date` on 2026-09-01. Aug 31 URLs may already return **403** from a laptop — try from **inside the cluster** (`hccm-prod`).

If 403: ask the ingress team whether the object still exists at `s3://insights-ingress-prod/{request_id}`.

---

## Execution plan

### Phase 0 — Now (15 min)

- [x] Export **all 263** hits → `state-farm-downloading-payload-raw.json`
- [x] Parse script → `parse_kibana_state_farm_logs.py`
- [x] Run parse and review `manifest.csv` / `manifest-midnight-only.csv`
- [x] Local download (262 payloads) via `download_payloads.py`
- [x] Midnight subset in `payloads-midnight/` via `split_midnight_payloads.py`
- [ ] Test **1 download** of a recent URL (`X-Amz-Date=20260901*`) from inside the cluster (if re-exporting)

### Phase 1 — Full ES export (30 min)

**Base query** (Kibana Dev Tools):

```http
GET cwl-hccm-prod-*/_search
{
  "size": 500,
  "sort": [{ "@timestamp": "asc" }, { "_id": "asc" }],
  "query": {
    "bool": {
      "filter": [
        { "range": { "@timestamp": { "gte": "2026-08-31T22:00:00Z", "lte": "2026-09-01T23:59:59Z" } } }
      ],
      "must": [
        { "query_string": {
            "query": "\"Downloading Payload\" AND (16594026 OR 11439097)",
            "default_field": "@message"
        }}
      ]
    }
  },
  "_source": ["@timestamp", "@message", "@log_stream"]
}
```

Pagination: repeat with `search_after` using the last page's `sort` until `hits.hits` is empty.

Alternative: Kibana **Discover** → index `cwl-hccm-prod-*` → export CSV.

### Phase 2 — Parse + manifest (30 min)

```bash
cd scripts/incident
python3 parse_kibana_state_farm_logs.py
```

Produces: `manifest.csv`, `manifest-midnight-only.csv`, `urls.tsv`, `urls-midnight-only.tsv`

- [x] Python script: JSON → `manifest.csv`
- [x] Columns: `request_id`, `kafka_timestamp`, `log_timestamp`, `size`, `url`, `cluster_id`, `log_stream`, `x_amz_date`, `url_expires_utc`
- [x] Dedupe by `request_id`
- [x] Apply midnight filter (`size >= 100KB` + 00:00–02:00 UTC window)
- [x] Generate `manifest-midnight-only.csv` for final backup

### Phase 3 — Download (1–2 h)

- [x] Download from laptop (262/262 OK for exported set)
- [ ] Sort by `url_expires_utc` ascending (most urgent first) — for future re-runs
- [ ] Download from **inside** `hccm-prod` if laptop gets 403 (curl/wget in temp job or listener pod)
- [x] Log status per `request_id` in `download-log.csv`

```bash
oc project hccm-prod

# Single test (replace URL and request_id)
oc run sf-backup-test --rm -i --restart=Never \
  --image=registry.access.redhat.com/ubi9/ubi-minimal \
  --command -- curl -fsSL -o /tmp/test.tgz "PRESIGNED_URL" && ls -la /tmp/test.tgz
```

### Phase 4 — Upload to team bucket (30 min)

Suggested destination (confirm with Cody/Luke):

```
s3://hccm-prod-s3/incident-backup/state-farm/all/{request_id}.tgz
s3://hccm-prod-s3/incident-backup/state-farm/midnight/{request_id}.tgz
```

- [ ] Use namespace creds (`koku-aws` / `hccm-s3`)
- [ ] Upload `manifest.csv` + `manifest-midnight-only.csv` alongside `.tgz` files
- [ ] Post S3 prefix link + counts in the incident Slack thread

### Phase 5 — Handoff for reingest (Cody/David)

Deliver:

- S3 path for backups (`payloads/` = full set, `payloads-midnight/` = reingest scope)
- `manifest-midnight-only.csv` with `request_id` + `kafka_timestamp` + `size`
- Incident time window
- Note: original presigned URLs are likely expired; the backup copy is the durable artifact

---

## Useful queries (validation)

**Count by day:**

```http
GET cwl-hccm-prod-*/_search
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [{ "range": { "@timestamp": { "gte": "2026-08-31T22:00:00Z", "lte": "2026-09-01T23:59:59Z" } } }],
      "must": [{ "query_string": { "query": "\"Downloading Payload\" AND 16594026", "default_field": "@message" } }]
    }
  },
  "aggs": {
    "by_day": { "date_histogram": { "field": "@timestamp", "calendar_interval": "day" } }
  }
}
```

**Large payloads only (pre-midnight filter):**

Add to `must_not`:

```json
{ "regexp": { "@message": ".*'size': [0-9]{1,5},.*" } }
```

(excludes `size` with 1–5 digits = &lt; 100 KB in most cases)

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Expired URL (403) | Urgent download; fallback to ingress S3 by `request_id` |
| 263 ≠ midnight-only | `size` + time window filter; validate with Luke |
| Slow download / large pods | Parallel job with limit (e.g. 5 concurrent) |
| Presigned URL fails outside cluster | Run curl from `hccm-prod` |
| 24h ingress quarantine | Prioritize oldest URLs first |

---

## What to do NOW (order)

1. **Export the 263** — query above, `size: 500`, paginate if needed → save JSON in this folder
2. **Test 1 curl** in cluster with a `20260901*` URL (e.g. `e2c7eacccf1f44eab0c8ef15decb590c`)
3. **Notify Victor** on Slack: “263 Kibana hits, starting download; Aug 31 URLs expire ~22:00 UTC today”
4. **Run parse script** → `parse_kibana_state_farm_logs.py`
5. **Batch download** valid URLs → upload to `hccm-prod-s3`
6. **Split midnight** → `split_midnight_payloads.py` → upload `payloads-midnight/` separately

Do not wait for a perfect script before step 2 — the 24h window is the real blocker.

---

## References

- Kibana prod: `https://kibana.apps.crcp01ue1.o9m8.p1.openshiftapps.com`
- Index: `cwl-hccm-prod-*`
- Log source: `koku/masu/external/kafka_msg_handler.py` → `Downloading Payload for msg:`
- Namespace: `hccm-prod` / cluster `crcp01ue1`
- Broader team plan: S3 backup (item 1) + new Kafka path behind flag (item 2, Cody)

---

## Quick checklist (copy to Slack)

```
State Farm S3 backup — status
[x] 263 logs exported from Kibana (cwl-hccm-prod-*)
[x] manifest.csv with request_id + url + size
[x] midnight-only filtered (size >= 100KB, 00:00-02:00 UTC) — 32 payloads
[x] 262/262 downloaded locally (~1.1 GB full, ~190 MB midnight)
[ ] .tgz in s3://hccm-prod-s3/incident-backup/state-farm/
[ ] handoff to Cody with manifest-midnight-only.csv
```
