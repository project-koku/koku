# Local Development Environment

Full guide for bringing up the Cost Management stack locally, generating test data, and verifying the UI end-to-end. See [`AGENTS.md`](../AGENTS.md) for the always-on quick reference.

### Mode Selection

| I'm working on... | Start with |
|-------------------|------------|
| OCP cost models, distribution, UI summaries | On-prem mode |
| AWS/Azure/GCP data processing | SaaS mode (Trino) |
| API changes, serializers, views | Either (on-prem is faster) |
| New report endpoint for cloud provider | SaaS mode (need data) |
| SQL template changes | **Both** (test each mode) |

### On-Prem Mode (PostgreSQL-Only)

### Prerequisites

- Docker or Podman with Compose support (this doc uses `docker compose` syntax)
- The repos cloned as siblings: `koku/`, `koku-ui/`, `nise/`
- `USER_ID` and `GROUP_ID` set in `.env` (run `id -u` and `id -g`)

### Step 1: Start Backend Services

The minimal on-prem stack needs: `db`, `valkey`, `unleash`, `koku-server`,
`masu-server`, `koku-worker`, `koku-beat`. S4 is needed only during OCP data
ingestion (see Step 3).

```bash
cd $KOKU_ROOT  # or your koku repo path

# Ensure .env has USER_ID and GROUP_ID
grep -q USER_ID .env || echo "USER_ID=$(id -u)" >> .env
grep -q GROUP_ID .env || echo "GROUP_ID=$(id -g)" >> .env

# Start core services (no Trino, no S4 yet)
docker compose up -d db valkey unleash koku-server masu-server koku-worker koku-beat
```

**Common port conflicts:**
- Port `15432` (db): Check for stale test containers: `podman ps -a | grep 15432`
- Port `9000` (`s4-path-proxy` S3 API): Conflicts with the frontend dev server. Stop the
  frontend before starting the S4 stack, and stop `s4-path-proxy` before restarting the
  frontend. Stopping `s4` alone does **not** release port 9000.

Wait for services to be healthy:

```bash
# Check all services are running
docker compose ps

# Verify API responds
curl -s http://localhost:8000/api/cost-management/v1/status/ | python3 -m json.tool
```

### Step 2: Verify Test Customer and Sources

The `create_test_customer.py` script (run automatically on first boot) creates a
test customer (`org_id: 1234567`, `account_number: 10001`) with pre-configured
sources:

```bash
docker compose exec db psql -U postgres -d postgres -c \
  "SELECT source_id, name, source_type FROM api_sources ORDER BY source_id;"
```

Expected sources:

| source_id | name                      | type       | cluster_id / notes                |
|-----------|---------------------------|------------|-----------------------------------|
| 1         | Test AWS Source            | AWS-local  | Reads from `/tmp/local_bucket`    |
| 2         | Test OCP on AWS           | OCP        | `my-ocp-cluster-1`               |
| 3         | Test OCP on Azure         | OCP        | `my-ocp-cluster-2`               |
| 4         | Test OCP on Premises      | OCP        | `my-ocp-cluster-3`               |
| 5         | Test Azure Source         | Azure-local|                                   |
| 7         | Test GCP Source           | GCP-local  |                                   |
| 8         | Test OCP on GCP           | OCP        | `test-ocp-gcp-cluster`           |

To check provider UUIDs and cluster IDs:

```bash
docker compose exec db psql -U postgres -d postgres -c "
  SELECT p.uuid::text, p.name, p.type, a.credentials
  FROM api_provider p
  LEFT JOIN api_providerauthentication a ON p.authentication_id = a.id
  ORDER BY p.name;"
```

### Step 3: Generate and Ingest OCP Test Data

OCP data flows through S4 (S3-compatible local object storage). The nise tool generates realistic usage CSVs.

#### 3a. Start S4 (temporarily stop the frontend if it's on port 9000)

OCP ingestion requires `s4`, `s4-path-proxy`, and the S3 buckets. Containers talk to
`koku-s4-proxy:7480` via `S4_PROXY_ENDPOINT`; host-side scripts (nise, `aws` CLI) use
`S3_ENDPOINT` or default to `http://localhost:9000`.

```bash
# Kill frontend if running on port 9000
lsof -ti :9000 | xargs kill 2>/dev/null

# Start S4, path proxy, and create buckets (preferred)
make trino-stack-up

# Or manually:
# docker compose up -d s4 s4-path-proxy
# docker compose up -d --wait --no-deps s4 s4-path-proxy
# docker compose run --rm --no-deps create-s3-buckets
```

#### 3b. Generate OCP data with nise

The nise repo has example YAMLs under `examples/`. Use them as templates with
updated dates.

```bash
cd $WORKSPACE/nise  # sibling to koku repo

# Create a date-adapted YAML (copy from examples/ocp_on_aws/ocp_static_data.yml,
# update start_date/end_date to current month range)
# Example: start_date: 2026-01-18, end_date: 2026-02-17

# Generate OCP data to a local directory
S3_ACCESS_KEY=s4admin \
S3_SECRET_KEY=s4secret \
S3_BUCKET_NAME=ocp-ingress \
.venv/bin/nise report ocp \
  --static-report-file /tmp/ocp_static_data.yml \
  --ocp-cluster-id my-ocp-cluster-1 \
  --insights-upload /tmp/nise_ocp_output \
  --daily-reports
```

**Nise CLI reference:**

| Provider | Command | Key flags |
|----------|---------|-----------|
| OCP | `nise report ocp` | `--ocp-cluster-id`, `--static-report-file`, `--insights-upload DIR`, `--minio-upload URL`, `--daily-reports` |
| AWS | `nise report aws` | `--static-report-file`, `--aws-s3-bucket-name LOCAL_DIR`, `--aws-s3-report-name None` |
| Azure | `nise report azure` | `--static-report-file`, `--azure-container-name LOCAL_DIR`, `--azure-report-name NAME` |
| GCP | `nise report gcp` | `--static-report-file`, `--gcp-bucket-name LOCAL_DIR`, `-r` |

**Nise environment variables** (required for S3 upload):
- `S3_ACCESS_KEY` — S4 access key (`s4admin`)
- `S3_SECRET_KEY` — S4 secret key (`s4secret`)
- `S3_BUCKET_NAME` — Target bucket (`ocp-ingress`)

**Nise example YAMLs** (`$WORKSPACE/nise/examples/`):
- `ocp_on_aws/ocp_static_data.yml` — OCP cluster (4 nodes, 6 namespaces, no GPUs)
- `ocp_on_aws/aws_static_data.yml` — Matching AWS infrastructure (EC2, EBS, S3, RDS, etc.)
- `ocp_on_azure/` — OCP + Azure variants
- `ocp_on_gcp/` — OCP + GCP variants

The koku repo also has templates under `dev/scripts/nise_ymls/` with Jinja2 date
placeholders, rendered by `dev/scripts/render_nise_yamls.py`.

#### 3c. Package and upload OCP data to S4

```bash
PAYLOAD=$(python3 -c "import uuid; print(uuid.uuid4().hex)")

# Create tarballs for each month
cd /tmp/nise_ocp_output/my-ocp-cluster-1/20260101-20260201
tar czf /tmp/${PAYLOAD}.2026_01.tar.gz .

cd /tmp/nise_ocp_output/my-ocp-cluster-1/20260201-20260301
tar czf /tmp/${PAYLOAD}.2026_02.tar.gz .

# Upload to S4 (key names must NOT have .tar.gz extension)
docker run --rm --network koku_default \
  -e AWS_ACCESS_KEY_ID=s4admin \
  -e AWS_SECRET_ACCESS_KEY=s4secret \
  -v /tmp/${PAYLOAD}.2026_01.tar.gz:/data/${PAYLOAD}.2026_01 \
  -v /tmp/${PAYLOAD}.2026_02.tar.gz:/data/${PAYLOAD}.2026_02 \
  amazon/aws-cli:latest \
  --endpoint-url http://koku-s4-proxy:7480 \
  s3 cp /data/${PAYLOAD}.2026_01 s3://ocp-ingress/${PAYLOAD}.2026_01

docker run --rm --network koku_default \
  -e AWS_ACCESS_KEY_ID=s4admin \
  -e AWS_SECRET_ACCESS_KEY=s4secret \
  -v /tmp/${PAYLOAD}.2026_02.tar.gz:/data/${PAYLOAD}.2026_02 \
  amazon/aws-cli:latest \
  --endpoint-url http://koku-s4-proxy:7480 \
  s3 cp /data/${PAYLOAD}.2026_02 s3://ocp-ingress/${PAYLOAD}.2026_02
```

**CRITICAL:** The S4 object key must match exactly what the `ingest_ocp_payload`
endpoint expects: `{payload_name}.{YYYY_MM}` — **no `.tar.gz` extension**. The Masu
download code constructs a presigned URL using the payload name directly as the key.

#### 3d. Trigger OCP ingestion

```bash
# Enable OCP tags (required for tag-based cost models)
curl -s -X POST \
  -H "Content-Type: application/json" \
  -d '{"schema":"org1234567","action":"create","tag_keys":["environment","app","version","storageclass"],"provider_type":"ocp"}' \
  http://localhost:5042/api/cost-management/v1/enabled_tags/

# Trigger ingestion for each month
curl -s "http://localhost:5042/api/cost-management/v1/ingest_ocp_payload/?org_id=1234567&payload_name=${PAYLOAD}.2026_01"
curl -s "http://localhost:5042/api/cost-management/v1/ingest_ocp_payload/?org_id=1234567&payload_name=${PAYLOAD}.2026_02"
```

#### 3e. Monitor ingestion progress

```bash
# Watch masu-server for extraction status
docker compose logs --since=2m masu-server 2>&1 | grep -i "extract\|error"

# Watch worker for processing and summarization
docker compose logs --since=2m koku-worker 2>&1 | grep -iE "summary|rows|complete|error|cost_model"
```

Ingestion is complete when you see `manifest marked complete` in the worker logs.

#### 3f. Stop S4 after ingestion

```bash
# Frees port 9000 for the frontend (s4 alone does not bind 9000)
docker compose stop s4-path-proxy

# Optional: stop the S4 backend and UI as well
docker compose stop s4
```

### SaaS Mode (Trino Stack)

Use SaaS mode when working on AWS/Azure/GCP features or testing the full data pipeline.

#### Starting SaaS Mode

```bash
cd $KOKU_ROOT

# Start the full stack with Trino
make docker-up-min-trino

# Or manually (includes S4 path proxy and bucket creation):
make trino-stack-up
docker compose up -d koku-server masu-server koku-worker koku-beat
```

This starts additional services:
- **Trino** (port 8080) — SQL analytics engine for Parquet aggregation
- **Hive Metastore** (port 9083) — Schema registry for Trino
- **s4-path-proxy** (port 9000) — S3 API proxy used by workers and host uploads
- **S4** (port 9001 S3 backend, port 5002 UI) — S3-compatible storage backend

#### Generate AWS/Azure/GCP Test Data

Cloud data goes to local directories mapped into the worker container:

| Provider   | Host path                                    | Container path             |
|------------|----------------------------------------------|----------------------------|
| AWS-local  | `testing/local_providers/aws_local/`         | `/tmp/local_bucket`        |
| Azure-local| `testing/local_providers/azure_local/`       | `/tmp/local_container`     |
| GCP-local  | `testing/local_providers/gcp_local/`         | `/tmp/gcp_local_bucket`    |

```bash
# Generate AWS data
cd $WORKSPACE/nise
.venv/bin/nise report aws \
  --static-report-file /tmp/aws_static_data.yml \
  --aws-s3-report-name None \
  --aws-s3-bucket-name $KOKU_ROOT/testing/local_providers/aws_local

# Trigger download and processing
curl -s "http://localhost:5042/api/cost-management/v1/download/?provider_uuid=<AWS_PROVIDER_UUID>"
```

#### Verifying Trino Is Working

```bash
# Check Trino is healthy
curl -s http://localhost:8080/v1/info | python3 -m json.tool

# Connect to Trino CLI (optional)
docker compose exec trino trino --catalog hive --schema org1234567
```

#### When Trino SQL Changes

After modifying `trino_sql/` templates:
1. Restart the worker to pick up changes: `docker compose restart koku-worker`
2. Trigger a re-summarization or re-ingest to execute the new SQL
3. Check worker logs for SQL errors: `docker compose logs koku-worker | grep -i error`

> **Note:** On-prem mode (`ONPREM=True`) cannot process AWS/Azure/GCP data.
> Those processors throw `NotImplementedError: ...does not implement write_to_self_hosted_table`.

### Step 5: Set Up Cost Models

Cost models define rates that convert usage data into dollar costs. Without rates,
all cost values will be `0.00`. The test customer has pre-created cost models, but
they may have **empty rates** by default.

#### Check existing cost models

```bash
docker compose exec db psql -U postgres -d postgres -c "
  SELECT cm.name, cm.source_type, cm.rates
  FROM \"org1234567\".cost_model cm;"
```

#### Update cost model with rates via API

```bash
IDENTITY=$(echo -n '{"identity":{"account_number":"10001","org_id":"1234567","type":"User","user":{"username":"user_dev","email":"user_dev@foo.com","is_org_admin":true,"access":{}}},"entitlements":{"cost_management":{"is_entitled":true}}}' | base64 -w0)

curl -s -X PUT \
  -H "x-rh-identity: $IDENTITY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Cost Management OpenShift on AWS Cost Model",
    "description": "OCP on AWS with supplementary rates",
    "source_type": "OCP",
    "source_uuids": ["<PROVIDER_UUID>"],
    "distribution": "cpu",
    "distribution_info": {
      "distribution_type": "cpu",
      "platform_cost": true,
      "worker_cost": true
    },
    "rates": [
      {"metric":{"name":"cpu_core_usage_per_hour"},"tiered_rates":[{"unit":"USD","value":0.007}],"cost_type":"Supplementary","name":"CPU usage"},
      {"metric":{"name":"cpu_core_request_per_hour"},"tiered_rates":[{"unit":"USD","value":0.2}],"cost_type":"Supplementary","name":"CPU request"},
      {"metric":{"name":"memory_gb_usage_per_hour"},"tiered_rates":[{"unit":"USD","value":0.009}],"cost_type":"Supplementary","name":"Memory usage"},
      {"metric":{"name":"memory_gb_request_per_hour"},"tiered_rates":[{"unit":"USD","value":0.05}],"cost_type":"Supplementary","name":"Memory request"},
      {"metric":{"name":"storage_gb_usage_per_month"},"tiered_rates":[{"unit":"USD","value":0.01}],"cost_type":"Supplementary","name":"Storage usage"},
      {"metric":{"name":"storage_gb_request_per_month"},"tiered_rates":[{"unit":"USD","value":0.01}],"cost_type":"Supplementary","name":"Storage request"},
      {"metric":{"name":"node_cost_per_month"},"tiered_rates":[{"unit":"USD","value":1000}],"cost_type":"Infrastructure","name":"Node cost"},
      {"metric":{"name":"cluster_cost_per_month"},"tiered_rates":[{"unit":"USD","value":10000}],"cost_type":"Infrastructure","name":"Cluster cost"}
    ],
    "markup": {"value": 10, "unit": "percent"}
  }' \
  "http://localhost:8000/api/cost-management/v1/cost-models/<COST_MODEL_UUID>/"
```

**Important:** Each rate object MUST include a `name` field (string) — the API
returns `400: "This field is required"` without it.

Updating a cost model via the API automatically triggers a cost recalculation
in the worker. You can also trigger it manually:

```bash
curl -s "http://localhost:5042/api/cost-management/v1/update_cost_model_costs/?provider_uuid=<UUID>&schema=org1234567"
```

Pre-built cost model JSON files are in `dev/scripts/cost_models/`:
- `openshift_on_prem_cost_model.json` — Full OCP rates (CPU, memory, storage, node, cluster, tags)
- `openshift_on_aws_cost_model.json` — Markup-only (10%, empty rates by default)
- `aws_cost_model.json`, `azure_cost_model.json`, `gcp_cost_model.json`

### Step 6: Start the Frontend

```bash
cd $WORKSPACE/koku-ui

# Build the identity token
IDENTITY=$(echo -n '{"identity":{"account_number":"10001","org_id":"1234567","type":"User","user":{"username":"user_dev","email":"user_dev@foo.com","is_org_admin":true,"access":{}}},"entitlements":{"cost_management":{"is_entitled":true}}}' | base64 -w0)

API_PROXY_URL=http://localhost:8000 \
API_TOKEN=$IDENTITY \
npm run start --workspace apps/koku-ui-onprem
```

The frontend starts at `http://localhost:9000/`. The webpack dev server proxies
`/api/cost-management/v1/*` to the backend at `http://localhost:8000`.

**Proxy configuration** (`apps/koku-ui-onprem/webpack.config.ts`):
- The proxy sends the identity via the `x-rh-identity` header (set from `API_TOKEN`)
- The proxy must NOT rewrite the path — the backend expects the full
  `/api/cost-management/v1/...` prefix

**Port 9000 conflict with S4:** The frontend and `s4-path-proxy` both use port 9000.
Never run them simultaneously. Stop `s4-path-proxy` before starting the frontend, and
vice versa. Stopping `s4` alone does not release port 9000.

### Step 7: Verify Data in the API

```bash
IDENTITY=$(echo -n '{"identity":{"account_number":"10001","org_id":"1234567","type":"User","user":{"username":"user_dev","email":"user_dev@foo.com","is_org_admin":true,"access":{}}},"entitlements":{"cost_management":{"is_entitled":true}}}' | base64 -w0)

# Check OCP costs by project
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8000/api/cost-management/v1/reports/openshift/costs/?filter[time_scope_value]=-1&filter[time_scope_units]=month&group_by[project]=*' \
  | python3 -m json.tool

# Check OCP compute usage
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8000/api/cost-management/v1/reports/openshift/compute/?filter[time_scope_value]=-1&filter[time_scope_units]=month&group_by[cluster]=*' \
  | python3 -m json.tool
```

If costs are all `0.00` but usage values are non-zero, the cost model either has
empty rates or wasn't applied. Check the cost model (Step 5) and trigger a
recalculation.

### Useful Masu API Endpoints

All endpoints are on the Masu server (`http://localhost:5042/api/cost-management/v1/`):

| Endpoint | Method | Purpose | Key params |
|----------|--------|---------|------------|
| `ingest_ocp_payload/` | GET | Trigger OCP data ingestion from S3 | `org_id`, `payload_name` |
| `download/` | GET | Trigger provider data download | `provider_uuid` |
| `update_cost_model_costs/` | GET | Re-apply cost model rates | `provider_uuid`, `schema` |
| `enabled_tags/` | POST | Enable tag keys for filtering | `schema`, `tag_keys`, `provider_type`, `action` |
| `status/` | GET | Masu health check | — |

### Identity Header

All Koku API requests require an `x-rh-identity` header (base64-encoded JSON).
The development identity for the test customer:

```json
{
  "identity": {
    "account_number": "10001",
    "org_id": "1234567",
    "type": "User",
    "user": {
      "username": "user_dev",
      "email": "user_dev@foo.com",
      "is_org_admin": true,
      "access": {}
    }
  },
  "entitlements": {
    "cost_management": {
      "is_entitled": true
    }
  }
}
```

Generate the base64 token:

```bash
echo -n '<JSON above, minified>' | base64 -w0
```

When `DEVELOPMENT=True` is set in `.env`, the backend also reads
`DEVELOPMENT_IDENTITY` from `.env` as a fallback when no header is provided.
However, explicit headers are needed for the frontend proxy and direct API calls.

### Quick-Start Cheat Sheet

```bash
# 1. Start backend
cd $KOKU_ROOT
docker compose up -d db valkey unleash koku-server masu-server koku-worker koku-beat

# 2. Generate + ingest OCP data (stop frontend first if running)
lsof -ti :9000 | xargs kill 2>/dev/null
make trino-stack-up
# ... (generate nise data, upload to S4, trigger ingest — see Steps 3a-3e)
docker compose stop s4-path-proxy

# 3. Start frontend
cd $WORKSPACE/koku-ui
IDENTITY=$(echo -n '...' | base64 -w0)
API_PROXY_URL=http://localhost:8000 API_TOKEN=$IDENTITY npm run start --workspace apps/koku-ui-onprem

# 4. Open browser to http://localhost:9000/
```

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `address already in use :15432` | Stale test DB container | `podman stop koku-test-db` |
| `address already in use :9000` | Frontend or `s4-path-proxy` conflict | Kill the other process: `lsof -ti :9000 \| xargs kill`, or `docker compose stop s4-path-proxy` |
| S3 `404 Not Found` on ingest | Object key has `.tar.gz` extension | Upload without extension: key must be `payload.YYYY_MM` not `payload.YYYY_MM.tar.gz` |
| `make_bucket failed` / `InvalidAccessKeyId` | Wrong S3 credentials in `.env` | Use `S3_ACCESS_KEY=s4admin` and `S3_SECRET=s4secret` (not legacy MinIO keys) |
| OCP ingest fails / cannot resolve `koku-s4-proxy` | `s4-path-proxy` not running, or `S3_ENDPOINT` set to Docker hostname on host | Run `make trino-stack-up`; use `S4_PROXY_ENDPOINT` for Docker and omit `S3_ENDPOINT` (or `localhost:9000`) for host |
| Nise exits silently (code 0, no output) | Missing env vars for S3 upload | Set `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_NAME` before running nise |
| All costs `0.00` but usage non-zero | Cost model has empty `rates: []` | Update cost model with actual rates via API (Step 5) |
| `NotImplementedError: ...write_to_self_hosted_table` | AWS/Azure/GCP data in on-prem mode | On-prem only supports OCP data; use Trino stack for cloud providers |
| `operator does not exist: text ->> unknown` | GPU cost model SQL bug in on-prem | Use OCP data without GPU nodes (nise `ocp_on_aws` examples have no GPUs) |
| API returns `403 Forbidden` | Wrong identity header | Use `account_number: "10001"`, `org_id: "1234567"` (matches test customer) |
| Frontend proxy returns `404` | `pathRewrite` strips API prefix | Remove `pathRewrite` from `webpack.config.ts` — backend expects full `/api/cost-management/v1/` path |
| API returns correct data but UI shows stale values | Django `cache_page` + browser HTTP cache | Flush server cache: `docker exec koku_valkey redis-cli FLUSHALL`, then hard-refresh browser (`Ctrl+Shift+R`) |
| Breakdown values are cluster-wide instead of per-project | `_breakdown_query_filter` missing entity filter | Fixed: `_apply_entity_scope()` now checks `group_by`, `filter`, and `exact:` prefixed variants |

### Cache Flushing (Important!)

The Koku API uses Django `cache_page` (backed by Valkey/Redis) with a 1-hour
default TTL. After ANY backend code change that affects API responses, you MUST:

```bash
# 1. Restart the server (picks up code changes from mounted volume)
docker compose restart koku-server

# 2. Flush the server-side cache
docker exec koku_valkey redis-cli FLUSHALL

# 3. Hard-refresh the browser (Ctrl+Shift+R) to bypass browser HTTP cache
```

Forgetting step 2 or 3 is the #1 cause of "I fixed it but it's still broken".

### Resuming After a Reboot

```bash
cd $KOKU_ROOT

# Start the backend stack
docker compose up -d db valkey unleash koku-server masu-server koku-worker koku-beat

# Wait for services to be ready (~15 seconds)
sleep 15

# Flush cache to ensure fresh responses
docker exec koku_valkey redis-cli FLUSHALL

# Verify the API is responding
IDENTITY=$(echo -n '{"identity":{"account_number":"10001","org_id":"1234567","type":"User","user":{"username":"user_dev","email":"user_dev@foo.com","is_org_admin":true,"access":{}}},"entitlements":{"cost_management":{"is_entitled":true}}}' | base64 -w0)
curl -s -H "x-rh-identity: $IDENTITY" http://localhost:8000/api/cost-management/v1/reports/openshift/costs/ | python3 -c "import json,sys; d=json.load(sys.stdin); print('API OK, total:', d['meta']['total']['cost']['total']['value'])"

# Start the frontend (on-prem mode)
cd $WORKSPACE/koku-ui
# Kill anything on port 9000 first
lsof -ti :9000 | xargs kill 2>/dev/null || true
API_TOKEN=$(echo -n '{"identity":{"account_number":"10001","org_id":"1234567","type":"User","user":{"username":"user_dev","email":"user_dev@foo.com","is_org_admin":true,"access":{}}},"entitlements":{"cost_management":{"is_entitled":true}}}' | base64 -w0) npx webpack serve --config apps/koku-ui-onprem/webpack.config.ts &

# Open browser to http://localhost:9000/openshift/details
```

**Data and cost models persist** in the PostgreSQL volume across reboots —
no need to re-ingest or re-apply cost models.

### Database Queries for Debugging

```bash
# Connect to the development database
docker compose exec db psql -U postgres -d postgres

# Check sources and providers
SELECT source_id, name, source_type, koku_uuid FROM api_sources ORDER BY source_id;

# Check cost models and their rates
SELECT cm.name, cm.source_type, cm.rates FROM "org1234567".cost_model cm;

# Check cost model assignments
SELECT cm.name, cmp.provider_uuid::text
FROM "org1234567".cost_model cm
JOIN "org1234567".cost_model_map cmp ON cm.uuid = cmp.cost_model_id;

# Check OCP daily summary data (are costs populated?)
SELECT usage_start, cluster_id, namespace,
       SUM(pod_usage_cpu_core_hours) AS cpu_hours,
       SUM(cost_model_cpu_cost) AS cpu_cost,
       SUM(infrastructure_raw_cost) AS infra_cost
FROM "org1234567".reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= '2026-02-01'
GROUP BY usage_start, cluster_id, namespace
ORDER BY usage_start, namespace
LIMIT 20;

# Check manifest processing status
SELECT id, provider_id::text, assembly_id, num_total_files, num_processed_files, completed_datetime
FROM reporting_common_costusagereportmanifest
ORDER BY id DESC LIMIT 10;
```
